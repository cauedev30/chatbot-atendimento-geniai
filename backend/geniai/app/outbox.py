import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from geniai.app.keyed_queue import KeyedQueue

if TYPE_CHECKING:
    from geniai.app.ports import Logger


async def safely(log: "Logger", what: str, fn: Callable[[], Awaitable[None]]) -> None:
    """Outbound calls never undo or block the database state (spec §10): the ticket is already written.
    Adapters retry; here the final failure is only logged.
    """
    try:
        await fn()
    except Exception as err:
        log.error({"err": err, "what": what}, "Chatwoot call failed")


class Outbox:
    """Chatwoot calls, one at a time per conversation and in the order they were asked for, always after
    the commit that caused them (spec §10). post() runs the call in the background, so a webhook answers
    without waiting for Chatwoot; run() waits for it."""

    def __init__(self) -> None:
        self._queue = KeyedQueue()
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self, log: "Logger", conversation_id: int, what: str, fn: Callable[[], Awaitable[None]]) -> None:
        await self._queue.run(f"chatwoot:{conversation_id}", lambda: safely(log, what, fn))

    def post(self, log: "Logger", conversation_id: int, what: str, fn: Callable[[], Awaitable[None]]) -> None:
        task = asyncio.create_task(self.run(log, conversation_id, what, fn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Waits for every posted call, including the ones posted meanwhile."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
