import asyncio
import itertools
import json
import time

import httpx
from sqlalchemy import select

from geniai.app.ports import LlmRequest
from geniai.app.process_turn import process_turn, run_turn
from geniai.db.schema import ticket, triage_message
from geniai.domain.texts import TEXT
from tests.api.conftest import WEBHOOK_TOKEN, Api
from tests.support.fakes import Sent, StatusSet, turn_json

_message_ids = itertools.count(1)
URL = f"/webhooks/chatwoot/{WEBHOOK_TOKEN}"


async def incoming(api: Api, conversation_id: int, text: str, phone: str = "+5511900000001") -> httpx.Response:
    return await api.client.post(
        URL,
        json={
            "event": "message_created",
            "id": next(_message_ids),
            "content": text,
            "message_type": "incoming",
            "conversation": {"id": conversation_id},
            "sender": {"phone_number": phone},
        },
    )


async def test_rejects_a_wrong_webhook_token(api: Api) -> None:
    res = await api.client.post("/webhooks/chatwoot/wrong", json={})
    assert res.status_code == 404


async def test_ignores_events_the_bot_does_not_use(api: Api) -> None:
    res = await api.client.post(
        URL,
        json={
            "event": "message_created",
            "id": 5,
            "content": "olá",
            "message_type": "outgoing",
            "conversation": {"id": 1},
        },
    )
    assert (res.status_code, res.json()) == (200, {"ignored": "not incoming"})


async def test_ignores_a_body_that_is_not_json(api: Api) -> None:
    res = await api.client.post(URL, content="not json", headers={"content-type": "application/json"})
    assert (res.status_code, res.json()) == (200, {"ignored": "not a Chatwoot event"})


async def test_runs_the_faq_flow_from_webhook_to_board(api: Api) -> None:
    h = api.h
    assert (await incoming(api, 45, "oi")).json() == {"outcome": "triage_ticket"}
    assert api.scheduler.scheduled == [45]
    assert await process_turn(h.deps, 45) == "greeting"

    await incoming(api, 45, "sim, esqueci a senha do painel")
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    assert await process_turn(h.deps, 45) == "send_faq"

    await incoming(api, 45, "deu certo, obrigado")
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    assert await process_turn(h.deps, 45) == "resolved_by_bot"

    await api.login()
    board = (await api.client.get("/api/board")).json()
    assert len(board["columns"]["resolved_by_bot"]) == 1


async def test_passes_the_conversation_status_through_so_a_reopened_conversation_goes_back_to_pending(
    api: Api,
) -> None:
    await api.client.post(
        URL,
        json={
            "event": "message_created",
            "id": next(_message_ids),
            "content": "oi de novo",
            "message_type": "incoming",
            "conversation": {"id": 47, "status": "open"},
            "sender": {"phone_number": "+5511900000001"},
        },
    )
    await api.h.settle()
    assert api.h.chatwoot.statuses == [StatusSet(47, "pending")]


async def test_closes_the_card_when_the_conversation_is_resolved_in_chatwoot(api: Api) -> None:
    assert (await incoming(api, 46, "socorro", "+5511900000099")).json() == {"outcome": "unidentified_ticket"}
    res = await api.client.post(URL, json={"event": "conversation_status_changed", "id": 46, "status": "resolved"})
    assert res.json() == {"moved": True}
    async with api.h.begin() as conn:
        row = (await conn.execute(select(ticket.c.column).where(ticket.c.chatwoot_conversation_id == 46))).one()
    assert row.column == "resolved_by_human"


async def test_the_webhook_needs_no_session_and_is_not_under_api(api: Api) -> None:
    assert (await api.client.post(f"/api/webhooks/chatwoot/{WEBHOOK_TOKEN}", json={})).status_code == 404


async def stored_texts(api: Api, conversation_id: int) -> list[str]:
    async with api.h.begin() as conn:
        query = (
            select(triage_message.c.text)
            .select_from(triage_message.join(ticket, triage_message.c.ticket_id == ticket.c.id))
            .where(ticket.c.chatwoot_conversation_id == conversation_id)
            .order_by(triage_message.c.id)
        )
        return list((await conn.execute(query)).scalars())


async def test_answers_at_once_while_a_turn_of_the_same_conversation_waits_on_the_llm(api: Api) -> None:
    h = api.h
    await incoming(api, 60, "oi")
    assert await process_turn(h.deps, 60) == "greeting"
    await incoming(api, 60, "o painel não abre")

    release = asyncio.Event()
    complete = h.llm.complete

    async def slow_llm(request: LlmRequest) -> str:
        await release.wait()  # a model that takes as long as the test wants
        return await complete(request)

    h.llm.complete = slow_llm  # type: ignore[method-assign]
    clarify = turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Aparece algum erro?")
    h.llm.push(clarify, clarify)
    turn = asyncio.create_task(run_turn(api.app.state.geniai.queue, h.deps, 60))
    await asyncio.sleep(0.05)
    assert not turn.done()

    started = time.perf_counter()
    res = await asyncio.wait_for(incoming(api, 60, "aparece erro 500"), timeout=1)
    assert time.perf_counter() - started < 1
    assert res.json() == {"outcome": "attached_to_triage"}
    assert "aparece erro 500" in await stored_texts(api, 60)

    release.set()
    assert await turn == "ask_clarification"
    assert "aparece erro 500" not in h.llm.requests[0].user
    # The message that arrived during the turn was not answered by it: the next turn takes it.
    assert await process_turn(h.deps, 60) == "ask_clarification"
    assert "aparece erro 500" in h.llm.requests[1].user


async def test_answers_without_waiting_for_chatwoot_and_calls_it_after_the_commit(api: Api) -> None:
    h = api.h
    release = asyncio.Event()
    send = h.chatwoot.send_message

    async def slow_send(conversation_id: int, text: str) -> None:
        await release.wait()
        await send(conversation_id, text)

    h.chatwoot.send_message = slow_send  # type: ignore[method-assign]
    started = time.perf_counter()
    res = await asyncio.wait_for(incoming(api, 61, "socorro", "+5511900000099"), timeout=1)
    assert time.perf_counter() - started < 1
    assert res.json() == {"outcome": "unidentified_ticket"}
    assert h.chatwoot.sent == []

    release.set()
    await h.settle()
    assert h.chatwoot.sent == [Sent(61, TEXT.unidentified_ack)]
    assert h.chatwoot.statuses == [StatusSet(61, "open")]


async def test_does_not_wait_for_a_turn_to_close_the_card_from_chatwoot(api: Api) -> None:
    h = api.h
    await incoming(api, 62, "oi")
    assert await process_turn(h.deps, 62) == "greeting"
    await incoming(api, 62, "o painel não abre")
    release = asyncio.Event()
    complete = h.llm.complete

    async def slow_llm(request: LlmRequest) -> str:
        await release.wait()
        return await complete(request)

    h.llm.complete = slow_llm  # type: ignore[method-assign]
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    turn = asyncio.create_task(run_turn(api.app.state.geniai.queue, h.deps, 62))
    await asyncio.sleep(0.05)

    status = {"event": "conversation_status_changed", "id": 62, "status": "resolved"}
    res = await asyncio.wait_for(api.client.post(URL, json=status), timeout=1)
    assert res.json() == {"moved": True}

    release.set()
    # The card left triage while the model was thinking: the turn drops its answer.
    assert await turn is None
    assert [s.text for s in h.chatwoot.sent][-1] != "Qual erro?"


async def test_logs_each_request_with_the_webhook_token_masked(api: Api) -> None:
    await incoming(api, 63, "oi")
    await api.client.post("/webhooks/chatwoot/um-token-errado-qualquer", json={})
    entries = [e.obj for e in api.h.logger.infos if e.msg == "request"]
    assert [(e["method"], e["path"], e["status"]) for e in entries] == [
        ("POST", "/webhooks/chatwoot/***", 200),
        ("POST", "/webhooks/chatwoot/***", 404),
    ]
    assert WEBHOOK_TOKEN not in json.dumps(entries)
    assert "um-token-errado-qualquer" not in json.dumps(entries)
