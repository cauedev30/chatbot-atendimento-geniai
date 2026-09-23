from typing import Final

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.api.schemas import Board, BoardCard, IdLabel, IdName
from geniai.app.notify import sync_chatwoot_status
from geniai.app.ports import Deps
from geniai.app.tickets_repo import (
    InvalidMoveError,
    MoveResult,
    TicketPatch,
    find_open_ticket,
    get_ticket,
    move_ticket,
    update_ticket,
)
from geniai.db.schema import category, team_member, ticket, unit
from geniai.domain.texts import category_label
from geniai.domain.types import BOARD_COLUMNS, BoardColumn, is_closed


class BoardError(Exception):
    """A refused board action; the message is shown to the support team (Portuguese)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


CLOSED_COLUMN_LIMIT: Final = 50
"""Closed columns only show the most recent cards; the indicators page covers history."""
OPEN_COLUMN_LIMIT: Final = 500

_UNIQUE_VIOLATION: Final = "23505"


def _is_unique_violation(err: BaseException) -> bool:
    """Postgres unique_violation, searched through the driver error and its cause chain."""
    seen: BaseException | None = err
    while seen is not None:
        if _UNIQUE_VIOLATION in (getattr(seen, "sqlstate", None), getattr(seen, "pgcode", None)):
            return True
        seen = getattr(seen, "orig", None) or seen.__cause__
    return False


async def load_board(deps: Deps) -> Board:
    async with deps.engine.connect() as conn:
        columns: dict[BoardColumn, list[BoardCard]] = {}
        for column in BOARD_COLUMNS:
            query = (
                select(
                    ticket.c.id,
                    unit.c.name.label("unit_name"),
                    ticket.c.category_id,
                    category.c.system.label("category_system"),
                    category.c.name.label("category_name"),
                    ticket.c.summary,
                    team_member.c.name.label("responsible_name"),
                    ticket.c.last_moved_at,
                    ticket.c.chatwoot_conversation_id,
                )
                .select_from(
                    ticket.outerjoin(unit, ticket.c.unit_id == unit.c.id)
                    .outerjoin(category, ticket.c.category_id == category.c.id)
                    .outerjoin(team_member, ticket.c.responsible_id == team_member.c.id)
                )
                .where(ticket.c.column == column)
                .order_by(ticket.c.last_moved_at.desc(), ticket.c.id.desc())
                .limit(CLOSED_COLUMN_LIMIT if is_closed(column) else OPEN_COLUMN_LIMIT)
            )
            columns[column] = [
                BoardCard(
                    id=r.id,
                    column=column,
                    unit_name=r.unit_name,
                    category_id=r.category_id,
                    category_label=(
                        category_label(r.category_system, r.category_name)
                        if r.category_system is not None and r.category_name is not None
                        else None
                    ),
                    summary=r.summary,
                    responsible_name=r.responsible_name,
                    last_moved_at=r.last_moved_at,
                    conversation_id=r.chatwoot_conversation_id,
                    conversation_url=deps.chatwoot.conversation_url(r.chatwoot_conversation_id),
                )
                for r in await conn.execute(query)
            ]
        triage_query = select(func.count()).select_from(ticket).where(ticket.c.column == "in_triage")
        triage_count = (await conn.execute(triage_query)).scalar_one()
        members_query = (
            select(team_member.c.id, team_member.c.name)
            .where(team_member.c.active.is_(True))
            .order_by(team_member.c.name)
        )
        team_members = [IdName(id=r.id, name=r.name) for r in await conn.execute(members_query)]
        categories_query = (
            select(category.c.id, category.c.system, category.c.name)
            .where(category.c.active.is_(True))
            .order_by(category.c.system, category.c.name)
        )
        categories = [
            IdLabel(id=r.id, label=category_label(r.system, r.name)) for r in await conn.execute(categories_query)
        ]
        await conn.rollback()
    return Board(
        generated_at=deps.now(),
        triage_count=triage_count,
        columns=columns,
        team_members=team_members,
        categories=categories,
        require_responsible=deps.rules.take_asks_who_takes,
    )


async def _move_in(
    deps: Deps, conn: AsyncConnection, ticket_id: int, to: BoardColumn, patch: TicketPatch | None = None
) -> MoveResult:
    try:
        return await move_ticket(conn, ticket_id, to, "human", deps.now(), patch)
    except InvalidMoveError as err:
        raise BoardError("Não foi possível mover este ticket.") from err
    except IntegrityError as err:
        # Reopening a closed card while its conversation already has another open ticket
        # violates ticket_one_open_per_conversation.
        if _is_unique_violation(err):
            raise BoardError("Esta conversa já tem outro ticket aberto.") from err
        raise


async def move_card(deps: Deps, ticket_id: int, to: BoardColumn, patch: TicketPatch | None = None) -> None:
    """A human move (drag, close, reopen), mirrored to the Chatwoot conversation status (spec §8)."""
    async with deps.engine.begin() as conn:
        result = await _move_in(deps, conn, ticket_id, to, patch)
    await sync_chatwoot_status(deps, result.ticket.chatwoot_conversation_id, result.from_, to)


async def take_card(deps: Deps, ticket_id: int, responsible_id: int | None) -> None:
    # OWNER-UNCONFIRMED: "take" asks who takes the ticket (rules.take_asks_who_takes).
    if responsible_id is None and deps.rules.take_asks_who_takes:
        raise BoardError("Escolha quem vai assumir o ticket.")
    async with deps.engine.begin() as conn:
        if responsible_id is not None:
            query = select(team_member.c.id).where(team_member.c.id == responsible_id, team_member.c.active.is_(True))
            if (await conn.execute(query)).first() is None:
                raise BoardError("Pessoa não encontrada.")
        current = await get_ticket(conn, ticket_id)
        if current is None:
            raise BoardError("Ticket não encontrado.")
        if current.column == "in_progress":
            await update_ticket(conn, ticket_id, {"responsible_id": responsible_id})
            return
        result = await _move_in(deps, conn, ticket_id, "in_progress", {"responsible_id": responsible_id})
    await sync_chatwoot_status(deps, result.ticket.chatwoot_conversation_id, result.from_, "in_progress")


async def recategorize(deps: Deps, ticket_id: int, category_id: int) -> None:
    """A human correction. bot_category_id keeps the agent's choice, which measures its accuracy."""
    async with deps.engine.begin() as conn:
        query = select(category.c.id).where(category.c.id == category_id, category.c.active.is_(True))
        if (await conn.execute(query)).first() is None:
            raise BoardError("Categoria não encontrada.")
        if await get_ticket(conn, ticket_id) is None:
            raise BoardError("Ticket não encontrado.")
        await update_ticket(conn, ticket_id, {"category_id": category_id})


async def on_conversation_resolved(deps: Deps, conversation_id: int) -> bool:
    """Resolving the conversation in Chatwoot closes the card (spec §8); no call back to Chatwoot."""
    async with deps.engine.begin() as conn:
        open_ticket = await find_open_ticket(conn, conversation_id)
        if open_ticket is None:
            return False
        await move_ticket(conn, open_ticket.id, "resolved_by_human", "human", deps.now())
    return True
