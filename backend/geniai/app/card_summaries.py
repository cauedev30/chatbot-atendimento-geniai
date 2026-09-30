import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any


async def _free_now() -> None:
    return None


class CardSummaries:
    """The card summaries being written in the background (see process_turn._fill_missing_summary). Each
    one is its own task, apart from the turn that handed over: it holds neither the conversation's turn
    nor a place among the running turns, and stop() cancels it with the rest of the app's work.

    `llm_free` returns once the LLM is free: main.py points it at the scheduler (no conversation in its
    burst window and no turn running); by default, as in the tests, it is free at once. A customer's turn
    never waits for a summary."""

    def __init__(self) -> None:
        self.llm_free: Callable[[], Awaitable[None]] = _free_now
        self._tasks: set[asyncio.Task[None]] = set()
        self._one_at_a_time = asyncio.Lock()

    def start(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @asynccontextmanager
    async def llm_turn(self) -> AsyncIterator[None]:
        """Waits until the LLM is free, one summary at a time, and holds it for one summary's call."""
        async with self._one_at_a_time:
            await self.llm_free()
            yield

    async def settle(self) -> None:
        """Waits for every summary started, also those started meanwhile."""
        while pending := [t for t in self._tasks if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def stop(self) -> None:
        """Cancels the summaries still waiting or running: stopping the app never waits for one."""
        for task in self._tasks:
            task.cancel()
        await self.settle()
