import itertools

import pytest
from sqlalchemy import select

from geniai.app.board import BoardError, load_board, move_card, on_conversation_resolved, recategorize, take_card
from geniai.app.tickets_repo import NewTicket, TicketRow, create_ticket, get_ticket, move_ticket, update_ticket
from geniai.db.schema import ticket_move
from tests.conftest import Harness
from tests.support.fakes import StatusSet

_conversations = itertools.count(1)


async def triage(h: Harness, conversation_id: int | None = None) -> int:
    ana = h.seed.attendants["ana"]
    async with h.begin() as conn:
        t = await create_ticket(
            conn,
            NewTicket(
                column="in_triage",
                conversation_id=conversation_id if conversation_id is not None else next(_conversations),
                phone_e164=ana.phone,
                attendant_id=ana.id,
                unit_id=ana.unit_id,
            ),
            h.now,
        )
    return t.id


async def awaiting(h: Harness, summary: str = "Painel não abre") -> int:
    ticket_id = await triage(h)
    login = h.seed.categories["login"]
    async with h.begin() as conn:
        await update_ticket(conn, ticket_id, {"summary": summary, "category_id": login, "bot_category_id": login})
        await move_ticket(conn, ticket_id, "awaiting_human", "bot", h.now, {"handoff_reason": "no_faq_match"})
    return ticket_id


async def fetch(h: Harness, ticket_id: int) -> TicketRow:
    async with h.begin() as conn:
        t = await get_ticket(conn, ticket_id)
    assert t is not None
    return t


# load_board


async def test_groups_cards_by_column_and_counts_conversations_still_with_the_bot(h: Harness) -> None:
    waiting = await awaiting(h)
    await triage(h)
    await triage(h)
    board = await load_board(h.deps)
    assert board.triage_count == 2
    assert list(board.columns) == [
        "resolved_by_bot",
        "awaiting_human",
        "in_progress",
        "resolved_by_human",
        "no_response",
    ]
    [card] = board.columns["awaiting_human"]
    assert card.id == waiting
    assert card.unit_name == "Unidade Exemplo Centro"
    assert card.category_label == "Painel / Não consegue entrar"
    assert card.summary == "Painel não abre"
    assert card.responsible_name is None
    assert card.conversation_url == h.chatwoot.conversation_url(card.conversation_id)
    assert board.columns["in_progress"] == []
    assert [m.name for m in board.team_members] == ["Pessoa Suporte 1", "Pessoa Suporte 2"]
    assert "Geral / Outros" in [c.label for c in board.categories]
    assert board.generated_at == h.now
    assert board.require_responsible is True


# take_card


async def test_asks_who_takes_the_ticket_owner_unconfirmed(h: Harness) -> None:
    ticket_id = await awaiting(h)
    with pytest.raises(BoardError):
        await take_card(h.deps, ticket_id, None)


async def test_sets_the_responsible_person_and_moves_to_in_progress(h: Harness) -> None:
    ticket_id = await awaiting(h)
    h.advance(10 * 60_000)
    await take_card(h.deps, ticket_id, h.seed.team["first"])
    t = await fetch(h, ticket_id)
    assert (t.column, t.responsible_id, t.taken_at) == ("in_progress", h.seed.team["first"], h.now)
    assert h.chatwoot.statuses == []


async def test_can_take_without_choosing_when_the_rule_is_off(h: Harness) -> None:
    h.with_rules(take_asks_who_takes=False)
    ticket_id = await awaiting(h)
    await take_card(h.deps, ticket_id, None)
    t = await fetch(h, ticket_id)
    assert (t.column, t.responsible_id) == ("in_progress", None)
    assert (await load_board(h.deps)).require_responsible is False


async def test_only_changes_the_responsible_person_of_a_card_already_in_progress(h: Harness) -> None:
    ticket_id = await awaiting(h)
    await take_card(h.deps, ticket_id, h.seed.team["first"])
    await take_card(h.deps, ticket_id, h.seed.team["second"])
    t = await fetch(h, ticket_id)
    assert (t.column, t.responsible_id) == ("in_progress", h.seed.team["second"])


async def test_refuses_an_unknown_person_or_ticket(h: Harness) -> None:
    ticket_id = await awaiting(h)
    with pytest.raises(BoardError, match=r"Pessoa não encontrada\."):
        await take_card(h.deps, ticket_id, 9999)
    with pytest.raises(BoardError, match=r"Ticket não encontrado\."):
        await take_card(h.deps, 9999, h.seed.team["first"])


# move_card


async def test_closing_resolves_the_chatwoot_conversation_and_records_a_human_move(h: Harness) -> None:
    ticket_id = await awaiting(h)
    await move_card(h.deps, ticket_id, "resolved_by_human")
    t = await fetch(h, ticket_id)
    assert (t.column, t.closed_at) == ("resolved_by_human", h.now)
    assert h.chatwoot.statuses == [StatusSet(t.chatwoot_conversation_id, "resolved")]
    async with h.begin() as conn:
        moves = (await conn.execute(select(ticket_move).where(ticket_move.c.ticket_id == ticket_id))).all()
    last = moves[-1]
    assert (last.from_column, last.to_column, last.actor) == ("awaiting_human", "resolved_by_human", "human")


async def test_reopening_opens_the_conversation_again(h: Harness) -> None:
    ticket_id = await awaiting(h)
    await move_card(h.deps, ticket_id, "resolved_by_human")
    await move_card(h.deps, ticket_id, "awaiting_human")
    assert (await fetch(h, ticket_id)).closed_at is None
    assert h.chatwoot.statuses[-1].status == "open"


async def test_refuses_to_reopen_a_card_whose_conversation_already_has_another_open_ticket(h: Harness) -> None:
    ticket_id = await awaiting(h)
    await move_card(h.deps, ticket_id, "resolved_by_human")
    closed = await fetch(h, ticket_id)
    await triage(h, closed.chatwoot_conversation_id)
    with pytest.raises(BoardError) as err:
        await move_card(h.deps, ticket_id, "awaiting_human")
    assert str(err.value) == "Esta conversa já tem outro ticket aberto."
    assert (await fetch(h, ticket_id)).column == "resolved_by_human"


async def test_refuses_a_move_to_the_same_column(h: Harness) -> None:
    ticket_id = await awaiting(h)
    with pytest.raises(BoardError, match=r"Não foi possível mover este ticket\."):
        await move_card(h.deps, ticket_id, "awaiting_human")


# recategorize


async def test_changes_the_category_and_keeps_the_agents_original_choice(h: Harness) -> None:
    ticket_id = await awaiting(h)
    await recategorize(h.deps, ticket_id, h.seed.categories["report"])
    t = await fetch(h, ticket_id)
    assert (t.category_id, t.bot_category_id) == (h.seed.categories["report"], h.seed.categories["login"])


async def test_rejects_an_unknown_category(h: Harness) -> None:
    ticket_id = await awaiting(h)
    with pytest.raises(BoardError, match=r"Categoria não encontrada\."):
        await recategorize(h.deps, ticket_id, 9999)


# on_conversation_resolved


async def test_moves_the_open_ticket_to_resolved_by_human_without_calling_chatwoot_back(h: Harness) -> None:
    ticket_id = await awaiting(h)
    t = await fetch(h, ticket_id)
    assert await on_conversation_resolved(h.deps, t.chatwoot_conversation_id) is True
    assert (await fetch(h, ticket_id)).column == "resolved_by_human"
    assert h.chatwoot.statuses == []


async def test_returns_false_when_the_conversation_has_no_open_ticket(h: Harness) -> None:
    assert await on_conversation_resolved(h.deps, 424242) is False
