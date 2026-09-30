from typing import Any

from geniai.chatwoot.webhook import ConversationResolved, Ignored, IncomingMessage, parse_chatwoot_event
from geniai.domain.types import Attachment

INCOMING: dict[str, Any] = {
    "event": "message_created",
    "id": 901,
    "content": "meu número caiu",
    "message_type": "incoming",
    "private": False,
    "conversation": {"id": 45, "status": "pending", "meta": {"sender": {"phone_number": "+5511900000001"}}},
    "sender": {"id": 9, "name": "Ana Exemplo", "phone_number": "+5511900000001", "type": "contact"},
    "attachments": [],
}


def test_reads_an_incoming_text_message() -> None:
    assert parse_chatwoot_event(INCOMING) == IncomingMessage(
        message_id=901,
        conversation_id=45,
        phone="+5511900000001",
        text="meu número caiu",
        conversation_status="pending",
    )


def test_reads_the_conversation_status_none_when_absent() -> None:
    resolved = INCOMING | {"conversation": INCOMING["conversation"] | {"status": "resolved"}}
    event = parse_chatwoot_event(resolved)
    assert isinstance(event, IncomingMessage)
    assert event.conversation_status == "resolved"
    event = parse_chatwoot_event(INCOMING | {"conversation": {"id": 45}})
    assert isinstance(event, IncomingMessage)
    assert event.conversation_status is None


def test_falls_back_to_the_conversation_sender_phone() -> None:
    event = parse_chatwoot_event(INCOMING | {"sender": {"id": 9, "type": "contact"}})
    assert isinstance(event, IncomingMessage)
    assert event.phone == "+5511900000001"


def test_gives_a_none_phone_when_there_is_none() -> None:
    event = parse_chatwoot_event(INCOMING | {"sender": {"id": 9}, "conversation": {"id": 45}})
    assert isinstance(event, IncomingMessage)
    assert event.phone is None


def test_reads_the_contact_identifier_from_the_sender_or_the_conversation() -> None:
    group = "120363000000000001@g.us"
    event = parse_chatwoot_event(INCOMING | {"sender": {"id": 9, "identifier": group, "phone_number": None}})
    assert isinstance(event, IncomingMessage)
    assert (event.phone, event.contact_identifier) == ("+5511900000001", group)
    meta = {"id": 45, "meta": {"sender": {"identifier": group}}}
    event = parse_chatwoot_event(INCOMING | {"sender": {"id": 9}, "conversation": meta})
    assert isinstance(event, IncomingMessage)
    assert (event.phone, event.contact_identifier) == (None, group)
    event = parse_chatwoot_event(INCOMING)
    assert isinstance(event, IncomingMessage)
    assert event.contact_identifier is None


def test_accepts_the_numeric_incoming_message_type() -> None:
    assert isinstance(parse_chatwoot_event(INCOMING | {"message_type": 0}), IncomingMessage)


def attachment(file_type: object, name: str = "foto.jpg", **fields: object) -> dict[str, object]:
    """An attachment in the documented Chatwoot shape, on an invented host."""
    return {
        "id": 77,
        "message_id": 901,
        "file_type": file_type,
        "account_id": 1,
        "extension": None,
        "data_url": f"https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/{name}",
        "thumb_url": f"https://chatwoot.example/rails/active_storage/representations/redirect/abc123/{name}",
        "file_size": 48213,
        **fields,
    }


def test_flags_media_without_text() -> None:
    event = parse_chatwoot_event(INCOMING | {"content": None, "attachments": [attachment("audio", "audio.ogg")]})
    assert isinstance(event, IncomingMessage)
    assert (event.text, event.has_media) == ("", True)
    assert event.attachments == (
        Attachment("audio", "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/audio.ogg"),
    )


def test_reads_each_attachment_with_its_kind_and_link_next_to_the_caption() -> None:
    files = [attachment("image"), attachment("video", "v.mp4"), attachment("file", "nota.pdf")]
    event = parse_chatwoot_event(INCOMING | {"content": "deu esse erro", "attachments": files})
    assert isinstance(event, IncomingMessage)
    assert event.text == "deu esse erro"
    assert [(a.kind, a.url) for a in event.attachments] == [
        ("image", "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/foto.jpg"),
        ("video", "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/v.mp4"),
        ("file", "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/nota.pdf"),
    ]


def test_an_unknown_or_missing_file_type_is_a_file_and_the_link_may_be_missing() -> None:
    files = [attachment("location"), attachment(None), {"id": 78}, attachment("image", data_url=None)]
    event = parse_chatwoot_event(INCOMING | {"content": "", "attachments": files})
    assert isinstance(event, IncomingMessage)
    assert [a.kind for a in event.attachments] == ["file", "file", "file", "image"]
    assert (event.attachments[2].url, event.attachments[3].url) == (None, None)


def test_a_malformed_attachment_link_is_dropped_not_the_message() -> None:
    event = parse_chatwoot_event(INCOMING | {"attachments": [attachment(3, data_url=42)]})
    assert isinstance(event, IncomingMessage)
    assert event.attachments == (Attachment("file", None),)


def test_ignores_outgoing_messages_and_private_notes() -> None:
    assert parse_chatwoot_event(INCOMING | {"message_type": "outgoing"}) == Ignored("not incoming")
    assert parse_chatwoot_event(INCOMING | {"private": True}) == Ignored("private note")


def test_reads_a_resolved_status_change_from_either_event_name() -> None:
    changed = {"event": "conversation_status_changed", "id": 45, "status": "resolved"}
    assert parse_chatwoot_event(changed) == ConversationResolved(conversation_id=45)
    assert parse_chatwoot_event({"event": "conversation_resolved", "id": 45}) == ConversationResolved(45)
    opened = {"event": "conversation_status_changed", "id": 45, "status": "open"}
    assert parse_chatwoot_event(opened) == Ignored("status open")


def test_ignores_anything_else() -> None:
    assert parse_chatwoot_event({"event": "webwidget_triggered"}) == Ignored("event webwidget_triggered")
    assert parse_chatwoot_event("garbage") == Ignored("not a Chatwoot event")


def test_ignores_empty_messages_and_unexpected_shapes() -> None:
    assert parse_chatwoot_event(INCOMING | {"content": "   "}) == Ignored("empty message")
    assert parse_chatwoot_event(INCOMING | {"id": "901"}) == Ignored("unexpected message_created shape")


def test_event_kinds_are_stable_names() -> None:
    assert [IncomingMessage.kind, ConversationResolved.kind, Ignored.kind] == [
        "incoming_message",
        "conversation_resolved",
        "ignored",
    ]


def test_a_null_status_change_is_not_a_status_and_closes_nothing() -> None:
    event = parse_chatwoot_event({"event": "conversation_status_changed", "id": 45, "status": None})
    assert event == Ignored("event conversation_status_changed")
    resolved_null = parse_chatwoot_event({"event": "conversation_resolved", "id": 45, "status": None})
    assert resolved_null == Ignored("event conversation_resolved")


def test_a_null_conversation_status_counts_as_absent() -> None:
    event = parse_chatwoot_event(INCOMING | {"conversation": {"id": 45, "status": None}})
    assert isinstance(event, IncomingMessage)
    assert event.conversation_status is None
