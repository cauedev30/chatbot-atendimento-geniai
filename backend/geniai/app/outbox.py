"""The transactional outbox (spec §10): every Chatwoot call is a row written in the same transaction as
the ticket change that causes it, so nothing is sent before the commit and nothing is lost when the
process stops. A worker sends the pending rows in order per conversation and marks each one sent, or
failed after the adapter's own retry rule (chatwoot/http.py)."""

import asyncio
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.db.schema import outbox

if TYPE_CHECKING:
    from geniai.app.ports import ChatwootStatus, Deps

POLL_S: Final = 5.0
"""The worker also looks for pending rows on this interval, whatever wakes it."""
BATCH: Final = 100
STOP_TIMEOUT_S: Final = 10.0


class Outbox:
    """Wakes the worker after a commit that wrote rows; the worker itself runs in main.py."""

    def __init__(self) -> None:
        self._wake = asyncio.Event()

    def wake(self) -> None:
        self._wake.set()

    async def wait(self, timeout_s: float) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout_s)
        except TimeoutError:
            pass
        self._wake.clear()


async def enqueue_message(conn: AsyncConnection, conversation_id: int, text: str) -> None:
    await conn.execute(insert(outbox).values(conversation_id=conversation_id, kind="message", payload=text))


async def enqueue_status(conn: AsyncConnection, conversation_id: int, status: "ChatwootStatus") -> None:
    await conn.execute(insert(outbox).values(conversation_id=conversation_id, kind="status", payload=status))


async def _finish(deps: "Deps", row_id: int, state: Literal["sent", "failed"], error: str | None = None) -> None:
    async with deps.engine.begin() as conn:
        await conn.execute(
            update(outbox).where(outbox.c.id == row_id).values(state=state, done_at=func.now(), error=error)
        )


async def _deliver_conversation(deps: "Deps", rows: list[tuple[int, str, str, int]]) -> None:
    for row_id, kind, payload, conversation_id in rows:
        try:
            if kind == "message":
                await deps.chatwoot.send_message(conversation_id, payload)
            else:
                await deps.chatwoot.set_status(conversation_id, payload)  # type: ignore[arg-type]
        except Exception as err:
            # Final: the adapter already repeated what was safe to repeat. The next rows still go out.
            deps.log.error({"err": err, "outboxId": row_id, "conversationId": conversation_id}, "Chatwoot call failed")
            await _finish(deps, row_id, "failed", str(err)[:500])
            continue
        await _finish(deps, row_id, "sent")


async def deliver_pending(deps: "Deps") -> int:
    """Sends every pending row: conversations in parallel, each one in id order. Returns how many rows
    were handled."""
    handled = 0
    while True:
        async with deps.engine.connect() as conn:
            query = (
                select(outbox.c.id, outbox.c.kind, outbox.c.payload, outbox.c.conversation_id)
                .where(outbox.c.state == "pending")
                .order_by(outbox.c.id)
                .limit(BATCH)
            )
            rows = [(r.id, r.kind, r.payload, r.conversation_id) for r in await conn.execute(query)]
            await conn.rollback()
        if not rows:
            return handled
        by_conversation: dict[int, list[tuple[int, str, str, int]]] = {}
        for row in rows:
            by_conversation.setdefault(row[3], []).append(row)
        await asyncio.gather(*(_deliver_conversation(deps, group) for group in by_conversation.values()))
        handled += len(rows)


class OutboxWorker:
    """Delivers at start (rows left pending by a stop), whenever woken, and every POLL_S seconds."""

    def __init__(self, deps: "Deps", poll_s: float = POLL_S) -> None:
        self._deps = deps
        self._poll_s = poll_s
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await deliver_pending(self._deps)
            except Exception as err:
                self._deps.log.error({"err": err}, "outbox delivery failed")
            if not self._stopping:
                await self._deps.outbox.wait(self._poll_s)

    async def stop(self, timeout_s: float = STOP_TIMEOUT_S) -> None:
        """Lets the current delivery finish, up to timeout_s; what is left stays pending for the next start."""
        self._stopping = True
        self._deps.outbox.wake()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout_s)
        except TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
