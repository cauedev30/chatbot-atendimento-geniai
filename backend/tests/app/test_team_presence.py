"""The bot stays out of a conversation where the team wrote since it was last closed (owner, 2026-10-05)."""

import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from geniai.app.board import on_conversation_resolved
from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.outbox import deliver_pending, enqueue_message
from geniai.app.ports import ChatwootMessage
from geniai.app.process_turn import process_turn
from geniai.app.tickets_repo import TicketRow
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.schema import ticket
from geniai.domain.texts import TEXT
from tests.conftest import Harness
from tests.support.fakes import StatusSet, turn_json

_message_ids = itertools.count(5000)
_conversations = itertools.count(700)


@pytest.fixture
def scheduler() -> RecordingScheduler:
    return RecordingScheduler()


def inbound(h: Harness, conversation_id: int, **overrides: Any) -> IncomingMessage:
    fields: dict[str, Any] = {
        "message_id": next(_message_ids),
        "conversation_id": conversation_id,
        "phone": h.seed.attendants["ana"].phone,
        "text": "oi",
        "conversation_status": "pending",
    }
    return IncomingMessage(**(fields | overrides))


def team_message(h: Harness, message_id: int, minutes: int = 0, **overrides: Any) -> ChatwootMessage:
    """A message of the team written `minutes` after the test clock's current time."""
    fields: dict[str, Any] = {
        "id": message_id,
        "at": h.now + timedelta(minutes=minutes),
        "outgoing": True,
        "private": False,
        "echo": False,
    }
    return ChatwootMessage(**(fields | overrides))


async def tickets_of(h: Harness, conversation_id: int) -> list[TicketRow]:
    async with h.begin() as conn:
        rows = await conn.execute(
            select(ticket).where(ticket.c.chatwoot_conversation_id == conversation_id).order_by(ticket.c.id)
        )
        return [TicketRow(**r._mapping) for r in rows]


def team_lines(h: Harness) -> list[dict[str, object]]:
    return [e.obj for e in h.logger.infos if e.msg == "team is talking"]


# No ticket open in the conversation


async def test_the_bot_stays_out_when_the_team_wrote_and_nobody_closed_the_conversation(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30)]
    outcome = await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id, text="voltou sim"))
    assert outcome == "team_talking"
    await h.settle()
    assert await tickets_of(h, conversation_id) == []
    assert h.chatwoot.sent == []
    assert h.chatwoot.statuses == [StatusSet(conversation_id, "open")]
    assert scheduler.scheduled == []
    assert team_lines(h) == [{"conversationId": conversation_id}]


async def test_a_repeated_delivery_of_that_message_is_a_duplicate(h: Harness, scheduler: RecordingScheduler) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30)]
    msg = inbound(h, conversation_id)
    assert await handle_inbound_message(h.deps, scheduler, msg) == "team_talking"
    assert await handle_inbound_message(h.deps, scheduler, msg) == "duplicate"


async def test_an_open_conversation_is_not_opened_again(h: Harness, scheduler: RecordingScheduler) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30)]
    msg = inbound(h, conversation_id, conversation_status="open")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "team_talking"
    await h.settle()
    assert h.chatwoot.statuses == []


async def test_the_bot_serves_again_once_the_team_resolved_the_conversation(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30)]
    await on_conversation_resolved(h.deps, conversation_id)
    h.advance(3 * 3600 * 1000)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    assert [t.column for t in await tickets_of(h, conversation_id)] == ["in_triage"]
    assert team_lines(h) == []


async def test_a_ticket_closed_after_the_team_wrote_lets_the_bot_serve(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    [first] = await tickets_of(h, conversation_id)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=1)]
    h.advance(5 * 60 * 1000)
    await on_conversation_resolved(h.deps, conversation_id)
    assert (await tickets_of(h, conversation_id))[0].column == "resolved_by_human"
    h.advance(60 * 1000)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    assert first.id != (await tickets_of(h, conversation_id))[-1].id


@pytest.mark.parametrize(
    "overrides",
    [{"echo": True}, {"private": True}, {"outgoing": False}],
    ids=["echo", "private note", "customer or activity"],
)
async def test_echoes_notes_and_other_messages_do_not_count(
    h: Harness, scheduler: RecordingScheduler, overrides: dict[str, Any]
) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30, **overrides)]
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"


async def test_a_message_the_bot_sent_does_not_count(h: Harness, scheduler: RecordingScheduler) -> None:
    conversation_id = next(_conversations)
    async with h.begin() as conn:
        await enqueue_message(conn, conversation_id, "Que bom que resolveu!")
    await deliver_pending(h.deps)
    h.chatwoot.messages[conversation_id] = [team_message(h, h.chatwoot.sent_ids[-1], minutes=-1)]
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"


async def test_carries_on_when_chatwoot_does_not_list_the_messages(h: Harness, scheduler: RecordingScheduler) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.fail_lists = True
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    [warning] = [e for e in h.logger.warnings if e.msg == "team check failed; the bot carries on"]
    assert warning.obj["conversationId"] == conversation_id


async def test_does_not_ask_chatwoot_when_a_ticket_is_open(h: Harness, scheduler: RecordingScheduler) -> None:
    conversation_id = next(_conversations)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    assert h.chatwoot.listed == [conversation_id]
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "attached_to_triage"
    assert h.chatwoot.listed == [conversation_id]


# A ticket in triage


async def test_a_ticket_in_triage_the_team_replied_to_goes_to_the_team_with_no_reply(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    assert await process_turn(h.deps, conversation_id) == "greeting"
    await h.settle()
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=1)]
    h.advance(2 * 60 * 1000)
    msg = inbound(h, conversation_id, text="sim, o painel não abre")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "attached_to_triage"
    # The card summary comes afterwards, like that of any handoff before the LLM.
    h.llm.push(turn_json(category_id=h.seed.categories["login"], summary="Painel não abre."))
    assert await process_turn(h.deps, conversation_id) == "handoff"
    await h.settle()
    [t] = await tickets_of(h, conversation_id)
    assert (t.column, t.handoff_reason) == ("awaiting_human", "team_replied")
    assert t.summary == "Painel não abre."
    assert [s.text for s in h.chatwoot.sent] == [TEXT.greeting("Ana Exemplo", "Unidade Exemplo Centro")]
    assert h.chatwoot.statuses[-1] == StatusSet(conversation_id, "open")
    assert team_lines(h) == [{"conversationId": conversation_id, "ticketId": t.id}]


async def test_a_team_message_before_the_ticket_opened_does_not_stop_the_turn(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    h.chatwoot.messages[conversation_id] = [team_message(h, 1, minutes=-30)]
    await on_conversation_resolved(h.deps, conversation_id)
    h.advance(60 * 1000)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    assert await process_turn(h.deps, conversation_id) == "greeting"


async def test_a_turn_carries_on_when_chatwoot_does_not_list_the_messages(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    conversation_id = next(_conversations)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id)) == "triage_ticket"
    h.chatwoot.fail_lists = True
    assert await process_turn(h.deps, conversation_id) == "greeting"
