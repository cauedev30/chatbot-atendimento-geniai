import itertools
from typing import Literal

from geniai.app.tickets_repo import NewTicket, TicketRow, create_ticket, get_ticket, move_ticket, update_ticket
from tests.api.conftest import Api

_conversations = itertools.count(1)


async def ticket_in(api: Api, column: Literal["in_triage", "awaiting_human"], summary: str = "Painel não abre") -> int:
    h = api.h
    ana = h.seed.attendants["ana"]
    login = h.seed.categories["login"]
    async with h.begin() as conn:
        t = await create_ticket(
            conn,
            NewTicket(
                column="in_triage",
                conversation_id=next(_conversations),
                phone_e164=ana.phone,
                attendant_id=ana.id,
                unit_id=ana.unit_id,
            ),
            h.now,
        )
        await update_ticket(conn, t.id, {"summary": summary, "category_id": login, "bot_category_id": login})
        if column == "awaiting_human":
            await move_ticket(conn, t.id, "awaiting_human", "bot", h.now, {"handoff_reason": "no_faq_match"})
    return t.id


async def fetch(api: Api, ticket_id: int) -> TicketRow:
    async with api.h.begin() as conn:
        t = await get_ticket(conn, ticket_id)
    assert t is not None
    return t


async def test_requires_login(api: Api) -> None:
    res = await api.client.get("/api/board")
    assert (res.status_code, res.json()) == (401, {"detail": "Faça login para continuar."})
    res = await api.client.post("/api/board/tickets/1/close", json={})
    assert res.status_code == 401


async def test_returns_the_columns_the_bot_counter_and_cards_with_the_chatwoot_link(logged_in: Api) -> None:
    waiting = await ticket_in(logged_in, "awaiting_human", "<b>painel</b> não abre")
    await ticket_in(logged_in, "in_triage")
    res = await logged_in.client.get("/api/board")
    assert res.status_code == 200
    board = res.json()
    assert list(board["columns"]) == [
        "resolved_by_bot",
        "awaiting_human",
        "in_progress",
        "resolved_by_human",
        "no_response",
    ]
    assert board["triageCount"] == 1
    assert board["requireResponsible"] is True
    assert board["generatedAt"].startswith("2026-09-23T15:00:00")
    [card] = board["columns"]["awaiting_human"]
    assert card["id"] == waiting
    assert card["summary"] == "<b>painel</b> não abre"
    assert card["unitName"] == "Unidade Exemplo Centro"
    assert card["categoryLabel"] == "Painel / Não consegue entrar"
    assert card["responsibleName"] is None
    assert card["column"] == "awaiting_human"
    assert card["conversationUrl"].startswith("https://chatwoot.example/app/accounts/1/conversations/")
    assert [m["name"] for m in board["teamMembers"]] == ["Pessoa Suporte 1", "Pessoa Suporte 2"]
    assert {"id", "label"} == set(board["categories"][0])


async def test_takes_a_ticket_for_the_chosen_person(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    first = logged_in.h.seed.team["first"]
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/take", json={"responsibleId": first})
    assert res.status_code == 204
    t = await fetch(logged_in, ticket_id)
    assert (t.column, t.responsible_id) == ("in_progress", first)


async def test_refuses_to_take_without_choosing_who(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/take", json={"responsibleId": None})
    assert (res.status_code, res.json()) == (400, {"detail": "Escolha quem vai assumir o ticket."})


async def test_moves_a_card_by_drag_and_drop_and_resolves_the_conversation_when_closed(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/move", json={"to": "resolved_by_human"})
    assert res.status_code == 204
    assert (await fetch(logged_in, ticket_id)).column == "resolved_by_human"
    assert logged_in.h.chatwoot.statuses[-1].status == "resolved"


async def test_rejects_a_move_into_triage(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/move", json={"to": "in_triage"})
    assert (res.status_code, res.json()) == (400, {"detail": "Pedido inválido."})


async def test_answers_400_not_500_when_reopening_a_card_whose_conversation_has_another_open_ticket(
    logged_in: Api,
) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    assert (await logged_in.client.post(f"/api/board/tickets/{ticket_id}/close", json={})).status_code == 204
    closed = await fetch(logged_in, ticket_id)
    ana = logged_in.h.seed.attendants["ana"]
    async with logged_in.h.begin() as conn:
        await create_ticket(
            conn,
            NewTicket(
                column="in_triage",
                conversation_id=closed.chatwoot_conversation_id,
                phone_e164=ana.phone,
                attendant_id=ana.id,
                unit_id=ana.unit_id,
            ),
            logged_in.h.now,
        )
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/move", json={"to": "awaiting_human"})
    assert (res.status_code, res.json()) == (400, {"detail": "Esta conversa já tem outro ticket aberto."})


async def test_corrects_the_category_and_closes(logged_in: Api) -> None:
    h = logged_in.h
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    report = h.seed.categories["report"]
    res = await logged_in.client.post(f"/api/board/tickets/{ticket_id}/category", json={"categoryId": report})
    assert res.status_code == 204
    assert (await logged_in.client.post(f"/api/board/tickets/{ticket_id}/close", json={})).status_code == 204
    t = await fetch(logged_in, ticket_id)
    assert (t.column, t.category_id, t.bot_category_id) == ("resolved_by_human", report, h.seed.categories["login"])


async def test_answers_pedido_invalido_to_a_malformed_body_or_path(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    for path, body in [
        (f"/api/board/tickets/{ticket_id}/category", {"categoryId": "abc"}),
        (f"/api/board/tickets/{ticket_id}/move", {}),
        ("/api/board/tickets/abc/close", None),
        ("/api/board/tickets/0/close", None),
    ]:
        res = await logged_in.client.post(path, json=body)
        assert (res.status_code, res.json()) == (400, {"detail": "Pedido inválido."}), path


async def test_accepts_json_mutations_only(logged_in: Api) -> None:
    ticket_id = await ticket_in(logged_in, "awaiting_human")
    res = await logged_in.client.post(
        f"/api/board/tickets/{ticket_id}/close", content="", headers={"content-type": "text/plain"}
    )
    assert (res.status_code, res.json()) == (400, {"detail": "Pedido inválido."})
    assert (await fetch(logged_in, ticket_id)).column == "awaiting_human"


async def test_reports_an_unknown_ticket(logged_in: Api) -> None:
    res = await logged_in.client.post("/api/board/tickets/9999/close", json={})
    assert (res.status_code, res.json()) == (400, {"detail": "Não foi possível mover este ticket."})
