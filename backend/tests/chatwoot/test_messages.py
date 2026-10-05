from datetime import UTC, datetime

import pytest

from geniai.app.ports import ChatwootMessage
from geniai.chatwoot.messages import parse_conversation_messages

AT = 1_700_000_000
WHEN = datetime.fromtimestamp(AT, UTC)


def body(*messages: object) -> dict[str, object]:
    return {"meta": {"labels": []}, "payload": list(messages)}


def test_reads_who_wrote_each_message() -> None:
    parsed = parse_conversation_messages(
        body(
            # A customer message.
            {"id": 1, "message_type": 0, "private": False, "created_at": AT, "sender": {"type": "contact"}},
            # A person of the team, or the bot (both use a user token).
            {"id": 2, "message_type": 1, "private": False, "created_at": AT, "sender": {"type": "user"}},
            # The connector's echo of a message sent.
            {
                "id": 3,
                "message_type": 1,
                "private": False,
                "created_at": AT,
                "sender": {"type": "agent_bot"},
                "content_attributes": {"external_echo": True},
            },
            # A private note, such as an audio transcript.
            {"id": 4, "message_type": 1, "private": True, "created_at": AT},
            # An activity, such as "the conversation was resolved".
            {"id": 5, "message_type": 2, "private": False, "created_at": AT},
        )
    )
    assert parsed == [
        ChatwootMessage(id=1, at=WHEN, outgoing=False, private=False, echo=False),
        ChatwootMessage(id=2, at=WHEN, outgoing=True, private=False, echo=False),
        ChatwootMessage(id=3, at=WHEN, outgoing=True, private=False, echo=True),
        ChatwootMessage(id=4, at=WHEN, outgoing=True, private=True, echo=False),
        ChatwootMessage(id=5, at=WHEN, outgoing=False, private=False, echo=False),
    ]


def test_accepts_the_message_type_as_text() -> None:
    parsed = parse_conversation_messages(body({"id": 2, "message_type": "outgoing", "created_at": AT}))
    assert parsed[0].outgoing is True


def test_skips_a_message_it_cannot_read() -> None:
    parsed = parse_conversation_messages(
        body({"id": 2, "message_type": 1}, {"id": "x"}, "texto", {"id": 3, "message_type": 1, "created_at": AT})
    )
    assert [m.id for m in parsed] == [3]


@pytest.mark.parametrize("raw", [None, [], {"payload": None}, {"meta": {}}])
def test_an_answer_without_the_list_of_messages_is_an_error(raw: object) -> None:
    with pytest.raises(ValueError):
        parse_conversation_messages(raw)
