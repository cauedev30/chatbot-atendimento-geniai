from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.db.schema import attendant, category, faq_item, ticket, ticket_move, triage_message, unit
from geniai.domain.transitions import TicketTimes, can_move, times_after_move
from geniai.domain.types import Actor, Column, HandoffReason, MessageAuthor


@dataclass(frozen=True)
class TicketRow:
    id: int
    attendant_id: int | None
    unit_id: int | None
    phone_e164: str | None
    column: Column
    category_id: int | None
    bot_category_id: int | None
    handoff_reason: HandoffReason | None
    faq_item_id: int | None
    faq_attempted: bool
    clarifications_asked: int
    unclear_feedback_reasks: int
    media_prompts: int
    summary: str
    responsible_id: int | None
    chatwoot_conversation_id: int
    opened_at: datetime
    handed_off_at: datetime | None
    taken_at: datetime | None
    closed_at: datetime | None
    last_customer_message_at: datetime
    last_moved_at: datetime


@dataclass(frozen=True)
class MessageRow:
    id: int
    ticket_id: int
    author: MessageAuthor
    text: str
    is_media: bool
    at: datetime
    chatwoot_message_id: int | None


TicketPatch = dict[str, object]
"""Ticket column names to new values; never `id` or `column` (checked by _check_patch)."""

OPEN_COLUMNS: Final[tuple[Column, ...]] = ("in_triage", "awaiting_human", "in_progress")

_PATCHABLE: Final = frozenset(ticket.c.keys()) - {"id", "column"}


class InvalidMoveError(Exception):
    pass


@dataclass(frozen=True)
class AttendantWithUnit:
    id: int
    name: str
    unit_id: int
    unit_name: str


@dataclass(frozen=True)
class CategoryRow:
    id: int
    key: str | None
    system: str
    name: str


@dataclass(frozen=True)
class FaqSummaryRow:
    id: int
    category_id: int
    title: str
    applies_when: str


@dataclass(frozen=True)
class FaqItemRow:
    id: int
    category_id: int
    title: str
    applies_when: str
    answer_text: str
    active: bool


def _check_patch(patch: TicketPatch) -> None:
    unknown = set(patch) - _PATCHABLE
    if unknown:
        raise ValueError(f"not a patchable ticket column: {', '.join(sorted(unknown))}")


def _ticket(row: Any) -> TicketRow:
    return TicketRow(**row._mapping)


async def message_exists(conn: AsyncConnection, chatwoot_message_id: int) -> bool:
    query = select(triage_message.c.id).where(triage_message.c.chatwoot_message_id == chatwoot_message_id).limit(1)
    return (await conn.execute(query)).first() is not None


_ATTENDANT_WITH_UNIT = select(
    attendant.c.id, attendant.c.name, unit.c.id.label("unit_id"), unit.c.name.label("unit_name")
).select_from(attendant.join(unit, attendant.c.unit_id == unit.c.id))


async def find_attendant_by_phone(conn: AsyncConnection, phone_e164: str) -> AttendantWithUnit | None:
    query = _ATTENDANT_WITH_UNIT.where(attendant.c.phone_e164 == phone_e164, attendant.c.active.is_(True)).limit(1)
    row = (await conn.execute(query)).first()
    return AttendantWithUnit(**row._mapping) if row else None


async def get_attendant_with_unit(conn: AsyncConnection, attendant_id: int) -> AttendantWithUnit:
    row = (await conn.execute(_ATTENDANT_WITH_UNIT.where(attendant.c.id == attendant_id).limit(1))).first()
    if row is None:
        raise LookupError(f"attendant {attendant_id} not found")
    return AttendantWithUnit(**row._mapping)


async def find_open_ticket(conn: AsyncConnection, conversation_id: int) -> TicketRow | None:
    query = (
        select(ticket)
        .where(ticket.c.chatwoot_conversation_id == conversation_id, ticket.c.column.in_(OPEN_COLUMNS))
        .limit(1)
    )
    row = (await conn.execute(query)).first()
    return _ticket(row) if row else None


async def get_ticket(conn: AsyncConnection, ticket_id: int) -> TicketRow | None:
    row = (await conn.execute(select(ticket).where(ticket.c.id == ticket_id).limit(1))).first()
    return _ticket(row) if row else None


async def get_category_id_by_key(conn: AsyncConnection, key: Literal["other", "unidentified"]) -> int:
    found = (await conn.execute(select(category.c.id).where(category.c.key == key).limit(1))).scalar_one_or_none()
    if found is None:
        raise LookupError(f'system category "{key}" is missing; run migrations')
    return int(found)


@dataclass(frozen=True)
class NewTicket:
    column: Literal["in_triage", "awaiting_human"]
    conversation_id: int
    phone_e164: str | None
    attendant_id: int | None
    unit_id: int | None
    category_id: int | None = None
    handoff_reason: HandoffReason | None = None
    summary: str = ""


async def create_ticket(conn: AsyncConnection, t: NewTicket, now: datetime) -> TicketRow:
    async with conn.begin_nested():
        query = (
            insert(ticket)
            .values(
                column=t.column,
                chatwoot_conversation_id=t.conversation_id,
                phone_e164=t.phone_e164,
                attendant_id=t.attendant_id,
                unit_id=t.unit_id,
                category_id=t.category_id,
                handoff_reason=t.handoff_reason,
                summary=t.summary,
                opened_at=now,
                last_moved_at=now,
                last_customer_message_at=now,
                handed_off_at=now if t.column == "awaiting_human" else None,
            )
            .returning(ticket)
        )
        created = _ticket((await conn.execute(query)).one())
        await conn.execute(
            insert(ticket_move).values(ticket_id=created.id, from_column=None, to_column=t.column, at=now, actor="bot")
        )
    return created


@dataclass(frozen=True)
class NewMessage:
    ticket_id: int
    author: MessageAuthor
    text: str
    at: datetime
    is_media: bool = False
    chatwoot_message_id: int | None = None


async def add_message(conn: AsyncConnection, m: NewMessage) -> bool:
    """Returns False when the Chatwoot message id was already stored (duplicate webhook)."""
    query = (
        pg_insert(triage_message)
        .values(
            ticket_id=m.ticket_id,
            author=m.author,
            text=m.text,
            is_media=m.is_media,
            chatwoot_message_id=m.chatwoot_message_id,
            at=m.at,
        )
        .on_conflict_do_nothing()
        .returning(triage_message.c.id)
    )
    return (await conn.execute(query)).first() is not None


async def list_messages(conn: AsyncConnection, ticket_id: int) -> list[MessageRow]:
    query = select(triage_message).where(triage_message.c.ticket_id == ticket_id).order_by(triage_message.c.id)
    return [MessageRow(**row._mapping) for row in await conn.execute(query)]


async def update_ticket(conn: AsyncConnection, ticket_id: int, patch: TicketPatch) -> None:
    _check_patch(patch)
    await conn.execute(update(ticket).where(ticket.c.id == ticket_id).values(**patch))


@dataclass(frozen=True)
class MoveResult:
    from_: Column
    ticket: TicketRow


async def move_ticket(
    conn: AsyncConnection,
    ticket_id: int,
    to: Column,
    actor: Actor,
    now: datetime,
    patch: TicketPatch | None = None,
) -> MoveResult:
    """Moves a ticket, stamps its times and records the move. Raises InvalidMoveError for a forbidden move."""
    patch = patch or {}
    _check_patch(patch)
    async with conn.begin_nested():
        current = await get_ticket(conn, ticket_id)
        if current is None:
            raise InvalidMoveError(f"ticket {ticket_id} not found")
        if not can_move(current.column, to, actor):
            raise InvalidMoveError(f"{actor} cannot move ticket {ticket_id} from {current.column} to {to}")
        times = times_after_move(to, now, TicketTimes(current.handed_off_at, current.taken_at, current.closed_at))
        values: dict[str, object] = {
            **patch,
            "handed_off_at": times.handed_off_at,
            "taken_at": times.taken_at,
            "closed_at": times.closed_at,
            "column": to,
            "last_moved_at": now,
        }
        query = update(ticket).where(ticket.c.id == ticket_id).values(**values).returning(ticket)
        moved = _ticket((await conn.execute(query)).one())
        await conn.execute(
            insert(ticket_move).values(
                ticket_id=ticket_id, from_column=current.column, to_column=to, at=now, actor=actor
            )
        )
    return MoveResult(from_=current.column, ticket=moved)


async def list_active_categories(conn: AsyncConnection) -> list[CategoryRow]:
    query = (
        select(category.c.id, category.c.key, category.c.system, category.c.name)
        .where(category.c.active.is_(True))
        .order_by(category.c.id)
    )
    return [CategoryRow(**row._mapping) for row in await conn.execute(query)]


async def list_active_faq_items(conn: AsyncConnection) -> list[FaqSummaryRow]:
    query = (
        select(faq_item.c.id, faq_item.c.category_id, faq_item.c.title, faq_item.c.applies_when)
        .where(faq_item.c.active.is_(True))
        .order_by(faq_item.c.id)
    )
    return [FaqSummaryRow(**row._mapping) for row in await conn.execute(query)]


async def get_faq_item(conn: AsyncConnection, faq_item_id: int) -> FaqItemRow | None:
    query = select(faq_item).where(faq_item.c.id == faq_item_id, faq_item.c.active.is_(True)).limit(1)
    row = (await conn.execute(query)).first()
    return FaqItemRow(**row._mapping) if row else None


async def list_tickets_in_column(conn: AsyncConnection, column: Column) -> list[TicketRow]:
    query = select(ticket).where(ticket.c.column == column).order_by(ticket.c.id)
    return [_ticket(row) for row in await conn.execute(query)]
