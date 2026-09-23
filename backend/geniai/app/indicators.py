from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import ColumnClause, ColumnElement, String, and_, extract, func, literal_column, select, true
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.api.schemas import (
    AgentHealth,
    CategoryCount,
    FaqHealth,
    Heatmap,
    HeatmapCell,
    HeatmapUnit,
    IdLabel,
    IdName,
    Indicators,
    Outcomes,
    PeriodCount,
    ReasonCount,
    TimeStats,
    UnitCount,
    Volume,
)
from geniai.app.ports import Deps
from geniai.app.tickets_repo import get_category_id_by_key
from geniai.db.schema import attendant, category, faq_item, ticket, unit
from geniai.domain.texts import category_label
from geniai.domain.types import BOARD_COLUMNS, BoardColumn


@dataclass(frozen=True)
class IndicatorFilter:
    from_: datetime
    """Inclusive start of the period, on ticket.opened_at."""
    to: datetime
    """Exclusive end of the period."""
    unit_id: int | None


# Literal time zone and formats (no bind parameters), so the same expression can appear in SELECT and
# GROUP BY: Postgres would see two different parameters otherwise.
WEEK: Final[ColumnClause[str]] = literal_column(
    "to_char(date_trunc('week', ticket.opened_at AT TIME ZONE 'America/Sao_Paulo'), 'YYYY-MM-DD')", String
)
MONTH: Final[ColumnClause[str]] = literal_column(
    "to_char(date_trunc('month', ticket.opened_at AT TIME ZONE 'America/Sao_Paulo'), 'YYYY-MM')", String
)


def _share(part: int, whole: int) -> float | None:
    return None if whole == 0 else part / whole


def _number(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def _count_where(condition: ColumnElement[bool]) -> ColumnElement[int]:
    return func.count().filter(condition)


def _minutes_between(
    later: ColumnElement[datetime], earlier: ColumnElement[datetime]
) -> ColumnElement[Decimal | float]:
    return extract("epoch", later - earlier) / 60


async def list_units(deps: Deps) -> list[IdName]:
    async with deps.engine.connect() as conn:
        rows = await conn.execute(select(unit.c.id, unit.c.name).where(unit.c.active.is_(True)).order_by(unit.c.name))
        units = [IdName(id=r.id, name=r.name) for r in rows]
        await conn.rollback()
    return units


async def compute_indicators(deps: Deps, f: IndicatorFilter) -> Indicators:
    async with deps.engine.connect() as conn:
        result = await _compute(conn, f)
        await conn.rollback()
    return result


async def _compute(conn: AsyncConnection, f: IndicatorFilter) -> Indicators:
    in_scope = and_(
        ticket.c.opened_at >= f.from_,
        ticket.c.opened_at < f.to,
        true() if f.unit_id is None else ticket.c.unit_id == f.unit_id,
    )
    reached = and_(in_scope, ticket.c.column != "in_triage")
    n = func.count()

    # 1. Volume
    by_week = [
        PeriodCount(period=r.period, count=r.total)
        for r in await conn.execute(
            select(WEEK.label("period"), n.label("total")).where(in_scope).group_by(WEEK).order_by(WEEK)
        )
    ]
    by_month = [
        PeriodCount(period=r.period, count=r.total)
        for r in await conn.execute(
            select(MONTH.label("period"), n.label("total")).where(in_scope).group_by(MONTH).order_by(MONTH)
        )
    ]
    by_unit = [
        UnitCount(unit_id=r.unit_id, unit_name=r.name, count=r.total)
        for r in await conn.execute(
            select(ticket.c.unit_id, unit.c.name, n.label("total"))
            .select_from(ticket.outerjoin(unit, ticket.c.unit_id == unit.c.id))
            .where(in_scope)
            .group_by(ticket.c.unit_id, unit.c.name)
            .order_by(n.desc())
        )
    ]
    by_category = [
        CategoryCount(
            category_id=r.category_id,
            label=category_label(r.system, r.name) if r.system is not None and r.name is not None else None,
            count=r.total,
        )
        for r in await conn.execute(
            select(ticket.c.category_id, category.c.system, category.c.name, n.label("total"))
            .select_from(ticket.outerjoin(category, ticket.c.category_id == category.c.id))
            .where(in_scope)
            .group_by(ticket.c.category_id, category.c.system, category.c.name)
            .order_by(n.desc())
        )
    ]

    # 2. Outcomes
    by_column: dict[BoardColumn, int] = dict.fromkeys(BOARD_COLUMNS, 0)
    for r in await conn.execute(select(ticket.c.column, n.label("total")).where(reached).group_by(ticket.c.column)):
        if r.column in by_column:
            by_column[r.column] = r.total
    by_handoff_reason = [
        ReasonCount(reason=r.reason, count=r.total)
        for r in await conn.execute(
            select(ticket.c.handoff_reason.label("reason"), n.label("total"))
            .where(in_scope, ticket.c.handoff_reason.is_not(None))
            .group_by(ticket.c.handoff_reason)
            .order_by(n.desc())
        )
    ]
    identified = (
        await conn.execute(
            select(
                n.label("reached"),
                _count_where(ticket.c.column == "resolved_by_bot").label("bot"),
                _count_where(ticket.c.column == "no_response").label("no_response"),
            ).where(reached, ticket.c.attendant_id.is_not(None))
        )
    ).one()

    # 3. Heatmap
    cells = [
        HeatmapCell(unit_id=r.unit_id, category_id=r.category_id, count=r.total)
        for r in await conn.execute(
            select(ticket.c.unit_id, ticket.c.category_id, n.label("total"))
            .where(in_scope, ticket.c.unit_id.is_not(None), ticket.c.category_id.is_not(None))
            .group_by(ticket.c.unit_id, ticket.c.category_id)
        )
    ]
    heatmap_units = [
        HeatmapUnit(id=r.id, name=r.name, attendants=r.attendants)
        for r in await conn.execute(
            select(unit.c.id, unit.c.name, func.count(attendant.c.id).filter(attendant.c.active).label("attendants"))
            .select_from(unit.outerjoin(attendant, attendant.c.unit_id == unit.c.id))
            .where(unit.c.active.is_(True) if f.unit_id is None else unit.c.id == f.unit_id)
            .group_by(unit.c.id, unit.c.name)
            .order_by(unit.c.name)
        )
    ]

    # 4. Time
    wait = _minutes_between(ticket.c.taken_at, ticket.c.handed_off_at)
    to_close = _minutes_between(ticket.c.closed_at, ticket.c.opened_at)
    wait_row = (
        await conn.execute(
            select(func.percentile_cont(0.5).within_group(wait).label("median"), func.avg(wait).label("avg")).where(
                in_scope, ticket.c.taken_at.is_not(None), ticket.c.handed_off_at.is_not(None)
            )
        )
    ).one()
    close_row = (
        await conn.execute(
            select(
                func.percentile_cont(0.5).within_group(to_close).label("median"), func.avg(to_close).label("avg")
            ).where(in_scope, ticket.c.closed_at.is_not(None))
        )
    ).one()

    # 5. FAQ health
    faq_rows = {
        r.faq_item_id: r
        for r in await conn.execute(
            select(
                ticket.c.faq_item_id,
                n.label("used"),
                _count_where(ticket.c.column == "resolved_by_bot").label("resolved"),
            )
            .where(in_scope, ticket.c.faq_attempted.is_(True))
            .group_by(ticket.c.faq_item_id)
        )
    }
    faq_health: list[FaqHealth] = []
    for faq in await conn.execute(
        select(faq_item.c.id, faq_item.c.title).where(faq_item.c.active.is_(True)).order_by(faq_item.c.id)
    ):
        row = faq_rows.get(faq.id)
        used = row.used if row is not None else 0
        resolved = row.resolved if row is not None else 0
        faq_health.append(
            FaqHealth(
                faq_item_id=faq.id, title=faq.title, used=used, resolved=resolved, resolved_share=_share(resolved, used)
            )
        )

    # 6. Agent health
    other_id = await get_category_id_by_key(conn, "other")
    agent = (
        await conn.execute(
            select(
                n.label("classified"),
                _count_where(ticket.c.category_id != ticket.c.bot_category_id).label("corrected"),
                _count_where(ticket.c.bot_category_id == other_id).label("other"),
            ).where(in_scope, ticket.c.bot_category_id.is_not(None))
        )
    ).one()

    return Indicators(
        volume=Volume(
            total=sum(u.count for u in by_unit),
            by_week=by_week,
            by_month=by_month,
            by_unit=by_unit,
            by_category=by_category,
        ),
        outcomes=Outcomes(
            by_column=by_column,
            by_handoff_reason=by_handoff_reason,
            identified_reached=identified.reached,
            bot_resolution_rate=_share(identified.bot, identified.reached),
            no_response_share=_share(identified.no_response, identified.reached),
        ),
        heatmap=Heatmap(
            units=heatmap_units,
            categories=[
                IdLabel(id=c.category_id, label=c.label)
                for c in by_category
                if c.category_id is not None and c.label is not None
            ],
            cells=cells,
        ),
        time=TimeStats(
            wait_to_take_median_min=_number(wait_row.median),
            wait_to_take_avg_min=_number(wait_row.avg),
            time_to_close_median_min=_number(close_row.median),
            time_to_close_avg_min=_number(close_row.avg),
        ),
        faq_health=faq_health,
        agent_health=AgentHealth(
            classified=agent.classified,
            corrected=agent.corrected,
            corrected_share=_share(agent.corrected, agent.classified),
            other_share=_share(agent.other, agent.classified),
        ),
    )
