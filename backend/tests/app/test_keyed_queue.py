import asyncio

import pytest

from geniai.app.keyed_queue import KeyedQueue, conversation_key


async def test_runs_tasks_with_the_same_key_one_after_another() -> None:
    queue = KeyedQueue()
    log: list[str] = []
    gate = asyncio.Event()

    async def a() -> None:
        log.append("a-start")
        await gate.wait()
        log.append("a-end")

    async def b() -> None:
        log.append("b")

    task_a = asyncio.create_task(queue.run("k", a))
    task_b = asyncio.create_task(queue.run("k", b))
    await asyncio.sleep(0.01)
    assert log == ["a-start"]
    gate.set()
    await asyncio.gather(task_a, task_b)
    assert log == ["a-start", "a-end", "b"]


async def test_does_not_block_other_keys() -> None:
    queue = KeyedQueue()
    never = asyncio.Event()

    async def blocked() -> None:
        await never.wait()

    async def done() -> str:
        return "done"

    pending = asyncio.create_task(queue.run("a", blocked))
    assert await asyncio.wait_for(queue.run("b", done), timeout=1) == "done"
    pending.cancel()


async def test_keeps_going_after_a_failed_task() -> None:
    queue = KeyedQueue()

    async def boom() -> None:
        raise RuntimeError("boom")

    async def one() -> int:
        return 1

    with pytest.raises(RuntimeError, match="boom"):
        await queue.run("k", boom)
    assert await queue.run("k", one) == 1


async def test_forgets_a_key_once_its_tasks_are_done() -> None:
    queue = KeyedQueue()

    async def one() -> int:
        return 1

    await queue.run("k", one)
    assert queue._locks == {}
    assert queue._users == {}


def test_conversation_key() -> None:
    assert conversation_key(45) == "conversation:45"
