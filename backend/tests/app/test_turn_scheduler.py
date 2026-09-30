"""Burst window, spec §5.1 step 1. A real 200 ms window stands in for the 5 s one, with the same
proportions and margins wide enough for the ~16 ms timer resolution of Windows."""

import asyncio

from geniai.app.turn_scheduler import DebouncedScheduler, RecordingScheduler

WINDOW_MS = 200


def at(fraction: float) -> float:
    """Seconds for a fraction of the window."""
    return WINDOW_MS * fraction / 1000


def ignore(_err: BaseException, _conversation_id: int) -> None:
    pass


async def test_runs_once_after_the_window_of_silence() -> None:
    runs: list[int] = []

    async def run(conversation_id: int) -> None:
        runs.append(conversation_id)

    scheduler = DebouncedScheduler(WINDOW_MS, run, ignore)
    scheduler.schedule(1)
    await asyncio.sleep(at(0.6))
    scheduler.schedule(1)
    await asyncio.sleep(at(0.6))
    assert runs == []
    await asyncio.sleep(at(0.6))
    assert runs == [1]
    await scheduler.stop()


async def test_keeps_conversations_independent() -> None:
    runs: list[int] = []

    async def run(conversation_id: int) -> None:
        runs.append(conversation_id)

    scheduler = DebouncedScheduler(WINDOW_MS, run, ignore)
    scheduler.schedule(1)
    await asyncio.sleep(at(0.8))
    scheduler.schedule(2)
    await asyncio.sleep(at(0.5))
    assert runs == [1]
    await asyncio.sleep(at(0.6))
    assert runs == [1, 2]
    await scheduler.stop()


async def test_reports_errors_instead_of_throwing() -> None:
    errors: list[int] = []

    async def boom(_: int) -> None:
        raise RuntimeError("boom")

    def on_error(_err: BaseException, conversation_id: int) -> None:
        errors.append(conversation_id)

    scheduler = DebouncedScheduler(10, boom, on_error)
    scheduler.schedule(7)
    await asyncio.sleep(0.1)
    assert errors == [7]
    await scheduler.stop()


async def test_stop_cancels_pending_runs() -> None:
    runs: list[int] = []

    async def run(conversation_id: int) -> None:
        runs.append(conversation_id)

    scheduler = DebouncedScheduler(WINDOW_MS, run, ignore)
    scheduler.schedule(1)
    await scheduler.stop()
    await asyncio.sleep(at(1.3))
    assert runs == []


async def test_stop_waits_for_runs_in_progress() -> None:
    finished: list[int] = []

    async def slow(conversation_id: int) -> None:
        await asyncio.sleep(0.05)
        finished.append(conversation_id)

    scheduler = DebouncedScheduler(10, slow, ignore)
    scheduler.schedule(3)
    await asyncio.sleep(0.03)
    await scheduler.stop()
    assert finished == [3]


def test_recording_scheduler_records_what_was_scheduled() -> None:
    scheduler = RecordingScheduler()
    scheduler.schedule(4)
    scheduler.schedule(4)
    assert scheduler.scheduled == [4, 4]


async def test_the_llm_is_free_only_with_no_conversation_in_its_window_and_no_turn_running() -> None:
    release = asyncio.Event()

    async def run(_: int) -> None:
        await release.wait()

    scheduler = DebouncedScheduler(WINDOW_MS, run, ignore)
    await asyncio.wait_for(scheduler.wait_idle(), timeout=at(0.1))
    scheduler.schedule(1)
    free = asyncio.create_task(scheduler.wait_idle())
    await asyncio.sleep(at(1.3))  # the window closed: the turn is running
    assert not free.done()
    release.set()
    await asyncio.wait_for(free, timeout=at(0.5))
    await scheduler.stop()


async def test_a_conversation_entering_its_window_keeps_the_llm_busy() -> None:
    async def run(_: int) -> None:
        pass

    scheduler = DebouncedScheduler(WINDOW_MS, run, ignore)
    scheduler.schedule(1)
    free = asyncio.create_task(scheduler.wait_idle())
    await asyncio.sleep(at(0.8))
    scheduler.schedule(2)
    await asyncio.sleep(at(0.5))  # 1 ran; 2 is still in its window
    assert not free.done()
    await asyncio.wait_for(free, timeout=at(1))
    await scheduler.stop()
