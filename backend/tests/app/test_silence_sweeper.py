import asyncio
import itertools
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.process_turn import process_turn
from geniai.app.silence_sweeper import resume_pending_turns, start_sweeper, sweep_silent_tickets
from geniai.app.tickets_repo import TicketRow, get_ticket, update_ticket
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.schema import ticket
from tests.conftest import Harness
from tests.support.fakes import StatusSet

HOUR = 3_600_000
_message_ids = itertools.count(1)


async def open_triage(h: Harness, conversation_id: int) -> TicketRow:
    msg = IncomingMessage(
        message_id=next(_message_ids),
        conversation_id=conversation_id,
        phone=h.seed.attendants["ana"].phone,
        text="oi",
        has_media=False,
        conversation_status=None,
    )
    await handle_inbound_message(h.deps, RecordingScheduler(), msg)
    async with h.begin() as conn:
        row = (await conn.execute(select(ticket).where(ticket.c.chatwoot_conversation_id == conversation_id))).one()
    return TicketRow(**row._mapping)


async def test_moves_a_silent_ticket_to_no_response_and_resolves_the_conversation(h: Harness) -> None:
    t = await open_triage(h, 1)
    h.advance(24 * HOUR)
    assert await sweep_silent_tickets(h.deps) == [t.id]
    async with h.begin() as conn:
        row = await get_ticket(conn, t.id)
    assert row is not None
    assert row.column == "no_response"
    assert h.chatwoot.statuses == [StatusSet(1, "resolved")]


async def test_keeps_tickets_with_a_recent_customer_message(h: Harness) -> None:
    await open_triage(h, 1)
    h.advance(23 * HOUR)
    assert await sweep_silent_tickets(h.deps) == []


async def test_can_spare_tickets_that_never_got_the_faq_hint_owner_unconfirmed(h: Harness) -> None:
    h.with_rules(silence_applies_before_faq=False)
    await open_triage(h, 1)
    with_faq = await open_triage(h, 2)
    async with h.begin() as conn:
        await update_ticket(conn, with_faq.id, {"faq_attempted": True})
    h.advance(25 * HOUR)
    assert await sweep_silent_tickets(h.deps) == [with_faq.id]


async def test_reschedules_only_conversations_with_unanswered_customer_messages(h: Harness) -> None:
    await open_triage(h, 1)
    await open_triage(h, 2)
    assert await process_turn(h.deps, 2) == "greeting"
    scheduler = RecordingScheduler()
    assert await resume_pending_turns(h.deps, scheduler) == 1
    assert scheduler.scheduled == [1]


async def eventually(check: Callable[[], Awaitable[bool]], attempts: int = 150) -> None:
    """Polls database-backed state (no event to wait on) every 20 ms, up to 3 s."""
    for _ in range(attempts):
        if await check():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


async def test_the_sweeper_task_sweeps_periodically_and_logs_errors(h: Harness) -> None:
    t = await open_triage(h, 1)
    h.advance(24 * HOUR)
    task = start_sweeper(h.deps, 0.05)

    async def swept() -> bool:
        async with h.begin() as conn:
            row = await get_ticket(conn, t.id)
        return row is not None and row.column == "no_response"

    async def logged() -> bool:
        return any(e.msg == "silence sweep failed" for e in h.logger.errors)

    try:
        await eventually(swept)
        h.deps.engine = None  # type: ignore[assignment]
        await eventually(logged)
        assert not task.done()
    finally:
        task.cancel()
        h.deps.engine = h.engine
