import asyncio

from geniai.app.notify import sync_chatwoot_status
from geniai.app.ports import Deps
from geniai.app.process_turn import pending_customer_messages
from geniai.app.tickets_repo import InvalidMoveError, list_messages, list_tickets_in_column, move_ticket
from geniai.app.turn_scheduler import TurnScheduler
from geniai.domain.silence import SilenceInput, is_silent


async def sweep_silent_tickets(deps: Deps) -> list[int]:
    """Spec §5.1 step 9: tickets in triage silent for the timeout go to "No response"."""
    now = deps.now()
    async with deps.engine.connect() as conn:
        in_triage = await list_tickets_in_column(conn, "in_triage")
        await conn.rollback()
    moved: list[int] = []
    for t in in_triage:
        if not is_silent(SilenceInput(t.column, t.faq_attempted, t.last_customer_message_at), now, deps.rules):
            continue
        try:
            async with deps.engine.begin() as conn:
                result = await move_ticket(conn, t.id, "no_response", "bot", now)
        except InvalidMoveError:
            # The ticket moved in the meantime (a message arrived); nothing to do.
            continue
        await sync_chatwoot_status(deps, t.chatwoot_conversation_id, result.from_, "no_response")
        moved.append(t.id)
    return moved


async def resume_pending_turns(deps: Deps, scheduler: TurnScheduler) -> int:
    """Burst timers live in memory; after a restart, reschedule every conversation with unanswered messages."""
    count = 0
    async with deps.engine.connect() as conn:
        for t in await list_tickets_in_column(conn, "in_triage"):
            if not pending_customer_messages(await list_messages(conn, t.id)):
                continue
            scheduler.schedule(t.chatwoot_conversation_id)
            count += 1
        await conn.rollback()
    return count


def start_sweeper(deps: Deps, interval_s: float) -> "asyncio.Task[None]":
    """Sleeps, then sweeps, forever. Errors are logged; cancel the task to stop it."""

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval_s)
            try:
                await sweep_silent_tickets(deps)
            except Exception as err:
                deps.log.error({"err": err}, "silence sweep failed")

    return asyncio.create_task(loop())
