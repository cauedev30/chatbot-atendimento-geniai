import asyncio

from geniai.app.outbox import Outbox
from tests.support.fakes import RecordingLogger


async def test_post_returns_at_once_and_drain_waits_for_the_call() -> None:
    outbox, log = Outbox(), RecordingLogger()
    gate, done = asyncio.Event(), []

    async def call() -> None:
        await gate.wait()
        done.append(1)

    outbox.post(log, 1, "send", call)
    await asyncio.sleep(0.01)
    assert done == []
    gate.set()
    await outbox.drain()
    assert done == [1]


async def test_keeps_the_order_of_one_conversation_and_does_not_block_others() -> None:
    outbox, log = Outbox(), RecordingLogger()
    gate, calls = asyncio.Event(), []

    async def slow_first() -> None:
        await gate.wait()
        calls.append("1a")

    async def record(name: str) -> None:
        calls.append(name)

    outbox.post(log, 1, "a", slow_first)
    outbox.post(log, 1, "b", lambda: record("1b"))
    outbox.post(log, 2, "c", lambda: record("2"))
    await asyncio.sleep(0.01)
    assert calls == ["2"]
    gate.set()
    await outbox.run(log, 1, "d", lambda: record("1c"))
    assert calls == ["2", "1a", "1b", "1c"]


async def test_logs_a_failed_call_and_keeps_going() -> None:
    outbox, log = Outbox(), RecordingLogger()
    calls: list[str] = []

    async def boom() -> None:
        raise RuntimeError("chatwoot unavailable")

    async def ok() -> None:
        calls.append("ok")

    outbox.post(log, 1, "send", boom)
    outbox.post(log, 1, "send", ok)
    await outbox.drain()
    assert calls == ["ok"]
    assert [e.obj["what"] for e in log.errors] == ["send"]
