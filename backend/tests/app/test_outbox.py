import asyncio

from sqlalchemy import select

from geniai.app.outbox import OutboxWorker, deliver_pending, enqueue_message, enqueue_status
from geniai.app.ports import ChatwootStatus
from geniai.db.schema import outbox
from tests.conftest import Harness
from tests.support.fakes import Sent, StatusSet


async def states(h: Harness) -> list[tuple[str, str | None]]:
    async with h.begin() as conn:
        rows = await conn.execute(select(outbox.c.state, outbox.c.error).order_by(outbox.c.id))
        return [(r.state, r.error) for r in rows]


async def test_sends_nothing_before_the_commit_and_nothing_after_a_rollback(h: Harness) -> None:
    class Rollback(Exception):
        pass

    try:
        async with h.begin() as conn:
            await enqueue_message(conn, 1, "olá")
            # Another connection, like the worker, does not see the row yet.
            await deliver_pending(h.deps)
            assert h.chatwoot.sent == []
            raise Rollback
    except Rollback:
        pass
    await deliver_pending(h.deps)
    assert h.chatwoot.sent == []
    assert await states(h) == []


async def test_sends_after_the_commit_and_marks_the_row_sent(h: Harness) -> None:
    async with h.begin() as conn:
        await enqueue_message(conn, 1, "olá")
        await enqueue_status(conn, 1, "open")
    assert await deliver_pending(h.deps) == 2
    assert h.chatwoot.sent == [Sent(1, "olá")]
    assert h.chatwoot.statuses == [StatusSet(1, "open")]
    assert await states(h) == [("sent", None), ("sent", None)]
    assert await deliver_pending(h.deps) == 0
    assert len(h.chatwoot.sent) == 1


async def test_a_new_worker_sends_what_a_stopped_process_left_pending(h: Harness) -> None:
    async with h.begin() as conn:
        await enqueue_message(conn, 1, "enviada depois do reinício")
    worker = OutboxWorker(h.deps, poll_s=60)
    worker.start()
    for _ in range(100):
        if h.chatwoot.sent:
            break
        await asyncio.sleep(0.01)
    await worker.stop()
    assert h.chatwoot.sent == [Sent(1, "enviada depois do reinício")]


async def test_keeps_the_order_of_one_conversation_and_does_not_block_others(h: Harness) -> None:
    gate = asyncio.Event()
    calls: list[str] = []
    send = h.chatwoot.send_message

    async def slow_first(conversation_id: int, text: str) -> None:
        if text == "1a":
            await gate.wait()
        calls.append(text)
        await send(conversation_id, text)

    h.chatwoot.send_message = slow_first  # type: ignore[method-assign]
    async with h.begin() as conn:
        await enqueue_message(conn, 1, "1a")
        await enqueue_message(conn, 1, "1b")
        await enqueue_message(conn, 2, "2")
    delivery = asyncio.create_task(deliver_pending(h.deps))
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0.01)
    assert calls == ["2"]
    gate.set()
    await delivery
    assert calls == ["2", "1a", "1b"]


async def test_marks_a_final_failure_logs_it_and_keeps_going(h: Harness) -> None:
    set_status = h.chatwoot.set_status

    async def failing(conversation_id: int, status: ChatwootStatus) -> None:
        if conversation_id == 1:
            raise RuntimeError("chatwoot unavailable")
        await set_status(conversation_id, status)

    h.chatwoot.set_status = failing  # type: ignore[method-assign]
    async with h.begin() as conn:
        await enqueue_status(conn, 1, "pending")
        await enqueue_message(conn, 1, "depois da falha")
        await enqueue_status(conn, 2, "open")
    await deliver_pending(h.deps)
    assert await states(h) == [("failed", "chatwoot unavailable"), ("sent", None), ("sent", None)]
    assert h.chatwoot.sent == [Sent(1, "depois da falha")]
    assert [e.obj["outboxId"] for e in h.logger.errors] == [1]
    # A failed row is not tried again.
    await deliver_pending(h.deps)
    assert len(h.logger.errors) == 1


async def test_stop_waits_a_limited_time_and_leaves_the_rest_pending(h: Harness) -> None:
    never = asyncio.Event()

    async def stuck(conversation_id: int, text: str) -> None:
        await never.wait()

    h.chatwoot.send_message = stuck  # type: ignore[method-assign]
    async with h.begin() as conn:
        await enqueue_message(conn, 1, "presa")
    worker = OutboxWorker(h.deps, poll_s=60)
    worker.start()
    await asyncio.sleep(0.05)
    await asyncio.wait_for(worker.stop(timeout_s=0.1), timeout=2)
    assert await states(h) == [("pending", None)]
