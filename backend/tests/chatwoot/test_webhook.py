from typing import Any

from geniai.chatwoot.webhook import ConversationResolved, Ignored, IncomingMessage, parse_chatwoot_event

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
        has_media=False,
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


def test_accepts_the_numeric_incoming_message_type() -> None:
    assert isinstance(parse_chatwoot_event(INCOMING | {"message_type": 0}), IncomingMessage)


def test_flags_media_without_text() -> None:
    event = parse_chatwoot_event(INCOMING | {"content": None, "attachments": [{"file_type": "audio"}]})
    assert isinstance(event, IncomingMessage)
    assert (event.text, event.has_media) == ("", True)


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
