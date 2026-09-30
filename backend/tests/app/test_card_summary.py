"""The card summary of a handoff decided before the LLM: apart from the turn, once the LLM is free.
A real 300 ms burst window stands in for the 4 s one, wide enough for the ~16 ms timer resolution of
Windows."""

import asyncio
import itertools

from sqlalchemy import select

from geniai.api.deps import AppState
from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.keyed_queue import KeyedQueue
from geniai.app.process_turn import process_turn, run_turn
from geniai.app.tickets_repo import TicketRow
from geniai.app.turn_scheduler import DebouncedScheduler, RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.config import load_config
from geniai.db.schema import ticket
from geniai.main import _running
from tests.api.test_config import VALID
from tests.conftest import Harness
from tests.support.fakes import turn_json

WINDOW_MS = 300
_message_ids = itertools.count(9_000)


async def receive(h: Harness, conversation_id: int, text: str) -> None:
    msg = IncomingMessage(
        message_id=next(_message_ids),
        conversation_id=conversation_id,
        phone=h.seed.attendants["ana"].phone,
        text=text,
        conversation_status=None,
    )
    await handle_inbound_message(h.deps, RecordingScheduler(), msg)


async def greeted(h: Harness, conversation_id: int) -> None:
    await receive(h, conversation_id, "oi")
    assert await process_turn(h.deps, conversation_id) == "greeting"


async def ticket_of(h: Harness, conversation_id: int) -> TicketRow:
    async with h.begin() as conn:
        query = select(ticket).where(ticket.c.chatwoot_conversation_id == conversation_id)
        return TicketRow(**(await conn.execute(query)).one()._mapping)


def summary_lines(h: Harness) -> list[dict[str, object]]:
    return [e.obj for e in h.logger.infos if e.msg == "card summary"]


def real_scheduler(h: Harness, errors: list[BaseException]) -> DebouncedScheduler:
    queue = KeyedQueue()

    async def turn(conversation_id: int) -> None:
        await run_turn(queue, h.deps, conversation_id)

    scheduler = DebouncedScheduler(WINDOW_MS, turn, lambda err, _: errors.append(err))
    h.deps.summaries.llm_free = scheduler.wait_idle
    return scheduler


async def test_the_summary_waits_for_a_conversation_in_its_window_and_starts_when_its_turn_ends(h: Harness) -> None:
    errors: list[BaseException] = []
    scheduler = real_scheduler(h, errors)
    await greeted(h, 501)
    await greeted(h, 502)
    login = h.seed.categories["login"]
    h.llm.push(
        turn_json(category_id=login, needs_clarification=True, reply="Aparece algum erro?"),
        turn_json(category_id=login, summary="Pede atendente; o painel não abre."),
    )
    await receive(h, 502, "o painel não abre")
    scheduler.schedule(502)

    await receive(h, 501, "quero falar com um atendente")
    assert await process_turn(h.deps, 501) == "handoff"
    await asyncio.sleep(WINDOW_MS * 0.5 / 1000)
    assert h.llm.requests == []  # the handoff was answered; its summary waits for 502

    await asyncio.wait_for(h.deps.summaries.settle(), timeout=2)
    assert "o painel não abre" in h.llm.requests[0].user
    assert "quero falar com um atendente" in h.llm.requests[1].user
    t = await ticket_of(h, 501)
    assert (t.summary, t.category_id, t.bot_category_id) == ("Pede atendente; o painel não abre.", login, login)
    [line] = summary_lines(h)
    assert set(line) == {"ticketId", "waitedMs", "llmMs", "llmOutcomes", "fallback"}
    assert (line["ticketId"], line["llmOutcomes"], line["fallback"]) == (t.id, ["ok"], False)
    assert isinstance(line["waitedMs"], int) and line["waitedMs"] >= WINDOW_MS * 0.4
    await scheduler.stop()
    assert errors == []


async def test_a_turn_during_the_wait_of_a_summary_calls_the_llm_at_once(h: Harness) -> None:
    never = asyncio.Event()
    h.deps.summaries.llm_free = never.wait  # the LLM never gets free for the summary
    await greeted(h, 511)
    await greeted(h, 512)
    await receive(h, 511, "quero falar com um atendente")
    assert await process_turn(h.deps, 511) == "handoff"

    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    await receive(h, 512, "o painel não abre")
    assert await asyncio.wait_for(process_turn(h.deps, 512), timeout=1) == "ask_clarification"
    assert [("o painel não abre" in r.user) for r in h.llm.requests] == [True]
    await h.deps.summaries.stop()


async def test_a_summary_past_its_deadline_keeps_the_customer_words(h: Harness) -> None:
    h.with_rules(summary_deadline_ms=100)
    never = asyncio.Event()
    h.deps.summaries.llm_free = never.wait
    await greeted(h, 521)
    await receive(h, 521, "quero falar com um atendente")
    assert await process_turn(h.deps, 521) == "handoff"

    await asyncio.wait_for(h.deps.summaries.settle(), timeout=2)
    assert h.llm.requests == []
    t = await ticket_of(h, 521)
    assert (t.summary, t.category_id) == ("oi / quero falar com um atendente", h.seed.categories["other"])
    [line] = summary_lines(h)
    assert (line["llmMs"], line["llmOutcomes"], line["fallback"]) == ([], [], True)
    assert isinstance(line["waitedMs"], int) and line["waitedMs"] >= 80


async def test_a_summary_the_llm_fails_keeps_the_customer_words_and_says_how_each_call_ended(h: Harness) -> None:
    await greeted(h, 531)
    h.llm.push(RuntimeError("down"), "not json")
    await receive(h, 531, "quero falar com um atendente")
    assert await process_turn(h.deps, 531) == "handoff"

    await asyncio.wait_for(h.deps.summaries.settle(), timeout=2)
    assert (await ticket_of(h, 531)).summary == "oi / quero falar com um atendente"
    [line] = summary_lines(h)
    assert (line["llmOutcomes"], line["fallback"], line["waitedMs"]) == (["error", "invalid"], True, 0)
    assert isinstance(line["llmMs"], list) and len(line["llmMs"]) == 2


async def test_stopping_the_app_does_not_wait_for_a_summary_waiting_for_the_llm(
    h: Harness, test_database_url: str
) -> None:
    state = AppState(config=load_config(VALID | {"DATABASE_URL": test_database_url}), queue=KeyedQueue())
    async with asyncio.timeout(2):
        async with _running(state, h.deps):
            assert state.scheduler is not None
            state.scheduler.schedule(999)  # a conversation in its burst window: the LLM is not free
            await receive(h, 541, "quero falar com um atendente")
            assert await process_turn(h.deps, 541) == "handoff"
            await asyncio.sleep(0.05)
            assert h.llm.requests == []
    assert h.llm.requests == []
    assert (await ticket_of(h, 541)).summary == ""
    assert summary_lines(h) == []
