import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Final
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from geniai.api.auth import require_login
from geniai.api.deps import app_deps
from geniai.api.schemas import ErrorOut, IndicatorsQueryOut, IndicatorsResponse
from geniai.app.indicators import IndicatorFilter, compute_indicators, list_units

SAO_PAULO: Final = ZoneInfo("America/Sao_Paulo")
"""São Paulo time from the IANA database (the tzdata package), past daylight saving included."""

_DATE: Final = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_POSITIVE_INT: Final = re.compile(r"^[0-9]+$")
MIN_YEAR: Final = 2000
MAX_YEAR: Final = 2100
"""Periods outside these years are refused: they are typos, and far dates overflow the calendar."""


@dataclass(frozen=True)
class IndicatorsQuery:
    from_date: str
    to_date: str
    unit_id: int | None
    normalize: bool
    filter: IndicatorFilter


def today_in_sao_paulo(now: datetime) -> str:
    return now.astimezone(SAO_PAULO).date().isoformat()


def _calendar_date(text: str) -> date | None:
    """A YYYY-MM-DD date between MIN_YEAR and MAX_YEAR: month 1-12 and day 1-31, where an impossible
    day rolls over into the next month ("2026-02-30" is March 2)."""
    match = _DATE.match(text)
    if match is None:
        return None
    year, month, day = (int(g) for g in match.groups())
    if not MIN_YEAR <= year <= MAX_YEAR or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return date(year, month, 1) + timedelta(days=day - 1)


def _sao_paulo_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=SAO_PAULO).astimezone(UTC)


def parse_indicators_query(params: Mapping[str, str], now: datetime) -> IndicatorsQuery | None:
    """The period is [from, to + 1 day) in São Paulo; the last 30 days by default."""
    raw_from, raw_to = params.get("from"), params.get("to")
    unit, norm = params.get("unit"), params.get("norm")
    if unit not in (None, "") and (unit is None or not _POSITIVE_INT.match(unit) or int(unit) == 0):
        return None
    if norm not in (None, "0", "1"):
        return None
    to_date = raw_to if raw_to is not None else today_in_sao_paulo(now)
    to_day = _calendar_date(to_date)
    if to_day is None:
        return None
    from_date = raw_from if raw_from is not None else (to_day - timedelta(days=29)).isoformat()
    from_day = _calendar_date(from_date)
    if from_day is None or from_date > to_date:
        return None
    unit_id = int(unit) if unit else None
    return IndicatorsQuery(
        from_date=from_date,
        to_date=to_date,
        unit_id=unit_id,
        normalize=norm == "1",
        filter=IndicatorFilter(
            from_=_sao_paulo_midnight(from_day), to=_sao_paulo_midnight(to_day + timedelta(days=1)), unit_id=unit_id
        ),
    )


router = APIRouter(prefix="/api/indicators", tags=["indicators"], dependencies=[Depends(require_login)])


@router.get("", responses={400: {"model": ErrorOut}, 401: {"model": ErrorOut}})
async def get_indicators(
    request: Request,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    unit: str | None = None,
    norm: str | None = None,
) -> IndicatorsResponse:
    deps = app_deps(request)
    params = {k: v for k, v in {"from": from_, "to": to, "unit": unit, "norm": norm}.items() if v is not None}
    q = parse_indicators_query(params, deps.now())
    if q is None:
        raise HTTPException(400, "Período inválido.")
    return IndicatorsResponse(
        query=IndicatorsQueryOut(from_date=q.from_date, to_date=q.to_date, unit_id=q.unit_id, normalize=q.normalize),
        units=await list_units(deps),
        data=await compute_indicators(deps, q.filter),
    )
