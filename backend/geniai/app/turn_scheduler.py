import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol


class TurnScheduler(Protocol):
    def schedule(self, conversation_id: int, *, bot_replied: bool) -> None:
        """bot_replied: the conversation's ticket already has a bot message (tickets_repo.has_bot_message)."""
        ...


class DebouncedScheduler:
    """Until the bot's first reply in the ticket, processes a conversation's turn only after window_ms
    without new messages, so a burst like "oi" / "bom dia" becomes one turn. Once the bot replied, the turn
    runs at once (owner, 2026-10-02); a message that arrives while a turn prepares its reply makes that
    reply be dropped instead (see process_turn._claim). Every caller follows this one rule.
    Timers live in memory; after a restart, resume_pending_turns() reschedules what was pending.
    It also knows when the LLM is free for background work (see wait_idle)."""

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
        self._idle = asyncio.Event()
        self._idle.set()

    def _is_idle(self) -> bool:
        return not self._timers and not self._running

    def _update_idle(self) -> None:
        if self._is_idle():
            self._idle.set()
        else:
            self._idle.clear()

    async def wait_idle(self) -> None:
        """Returns once no conversation is in its burst window and no turn is running: the LLM is free.
        Only background work waits for this (the card summary); a turn never does."""
        while not self._is_idle():
            await self._idle.wait()

    def schedule(self, conversation_id: int, *, bot_replied: bool) -> None:
        if (old := self._timers.pop(conversation_id, None)) is not None:
            old.cancel()
        window_s = 0 if bot_replied else self._window_s
        loop = asyncio.get_running_loop()
        self._timers[conversation_id] = loop.call_later(window_s, self._fire, conversation_id)
        self._update_idle()

    def _fire(self, conversation_id: int) -> None:
        self._timers.pop(conversation_id, None)
        task = asyncio.create_task(self._run_safely(conversation_id))
        self._running.add(task)
        task.add_done_callback(self._turn_done)
        self._update_idle()

    def _turn_done(self, task: asyncio.Task[None]) -> None:
        self._running.discard(task)
        self._update_idle()

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
        self._update_idle()


class RecordingScheduler:
    """Test double: records what was scheduled; tests call process_turn themselves."""

    def __init__(self) -> None:
        self.scheduled: list[int] = []
        self.bot_replied: list[bool] = []

    def schedule(self, conversation_id: int, *, bot_replied: bool) -> None:
        self.scheduled.append(conversation_id)
        self.bot_replied.append(bot_replied)
