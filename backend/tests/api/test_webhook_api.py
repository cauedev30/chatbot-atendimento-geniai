import itertools

import httpx
from sqlalchemy import select

from geniai.app.process_turn import process_turn
from geniai.db.schema import ticket
from tests.api.conftest import WEBHOOK_TOKEN, Api
from tests.support.fakes import StatusSet, turn_json

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
    assert api.h.chatwoot.statuses == [StatusSet(47, "pending")]


async def test_closes_the_card_when_the_conversation_is_resolved_in_chatwoot(api: Api) -> None:
    assert (await incoming(api, 46, "socorro", "+5511988887777")).json() == {"outcome": "unidentified_ticket"}
    res = await api.client.post(URL, json={"event": "conversation_status_changed", "id": 46, "status": "resolved"})
    assert res.json() == {"moved": True}
    async with api.h.begin() as conn:
        row = (await conn.execute(select(ticket.c.column).where(ticket.c.chatwoot_conversation_id == 46))).one()
    assert row.column == "resolved_by_human"


async def test_the_webhook_needs_no_session_and_is_not_under_api(api: Api) -> None:
    assert (await api.client.post(f"/api/webhooks/chatwoot/{WEBHOOK_TOKEN}", json={})).status_code == 404
