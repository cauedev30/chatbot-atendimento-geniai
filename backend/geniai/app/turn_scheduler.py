import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol


class TurnScheduler(Protocol):
    def schedule(self, conversation_id: int) -> None: ...


class DebouncedScheduler:
    """Processes a conversation's turn only after window_ms without new messages, so a burst like
    "oi" / "tudo bem?" / "meu número caiu" becomes one turn (OWNER-UNCONFIRMED window, see rules.py).
    Timers live in memory; after a restart, resume_pending_turns() reschedules what was pending."""

    def __init__(
        self,
        window_ms: int,
        run: Callable[[int], Awaitable[None]],
        on_error: Callable[[BaseException, int], None],
    ) -> None:
        self._window_s = window_ms / 1000
        self._run = run
        self._on_error = on_error
        self._timers: dict[int, asyncio.TimerHandle] = {}
        self._running: set[asyncio.Task[None]] = set()

    def schedule(self, conversation_id: int) -> None:
        if (old := self._timers.pop(conversation_id, None)) is not None:
            old.cancel()
        loop = asyncio.get_running_loop()
        self._timers[conversation_id] = loop.call_later(self._window_s, self._fire, conversation_id)

    def _fire(self, conversation_id: int) -> None:
        self._timers.pop(conversation_id, None)
        task = asyncio.create_task(self._run_safely(conversation_id))
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _run_safely(self, conversation_id: int) -> None:
        try:
            await self._run(conversation_id)
        except Exception as err:  # reported, never raised into the event loop
            self._on_error(err, conversation_id)

    async def stop(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)


class RecordingScheduler:
    """Test double: records what was scheduled; tests call process_turn themselves."""

    def __init__(self) -> None:
        self.scheduled: list[int] = []

    def schedule(self, conversation_id: int) -> None:
        self.scheduled.append(conversation_id)
