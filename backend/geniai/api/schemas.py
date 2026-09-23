"""The JSON models of the API contract. Fields are snake_case in Python and camelCase on the wire."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictStr
from pydantic.alias_generators import to_camel

from geniai.domain.types import BoardColumn, HandoffReason
from geniai.json_types import JsonInt


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class IdName(ApiModel):
    id: int
    name: str


class IdLabel(ApiModel):
    id: int
    label: str


# Board


class BoardCard(ApiModel):
    id: int
    column: BoardColumn
    unit_name: str | None
    category_id: int | None
    category_label: str | None
    summary: str
    responsible_name: str | None
    last_moved_at: datetime
    conversation_id: int
    conversation_url: str


class Board(ApiModel):
    generated_at: datetime
    """Server "now"; the client computes "há X min" from it."""
    triage_count: int
    columns: dict[BoardColumn, list[BoardCard]]
    """All five keys, in BOARD_COLUMNS order."""
    team_members: list[IdName]
    categories: list[IdLabel]
    require_responsible: bool
    """rules.take_asks_who_takes: "Assumir" must name who takes the ticket."""


# Indicators: the six blocks of spec §9


class PeriodCount(ApiModel):
    period: str
    count: int


class UnitCount(ApiModel):
    unit_id: int | None
    unit_name: str | None
    count: int


class CategoryCount(ApiModel):
    category_id: int | None
    label: str | None
    count: int


class Volume(ApiModel):
    total: int
    by_week: list[PeriodCount]
    by_month: list[PeriodCount]
    by_unit: list[UnitCount]
    by_category: list[CategoryCount]


class ReasonCount(ApiModel):
    reason: HandoffReason
    count: int


class Outcomes(ApiModel):
    by_column: dict[BoardColumn, int]
    by_handoff_reason: list[ReasonCount]
    identified_reached: int
    bot_resolution_rate: float | None
    """Resolved by the bot over identified tickets that reached a column; "no response" is not a success."""
    no_response_share: float | None


class HeatmapUnit(ApiModel):
    id: int
    name: str
    attendants: int


class HeatmapCell(ApiModel):
    unit_id: int
    category_id: int
    count: int


class Heatmap(ApiModel):
    units: list[HeatmapUnit]
    categories: list[IdLabel]
    cells: list[HeatmapCell]


class TimeStats(ApiModel):
    wait_to_take_median_min: float | None
    wait_to_take_avg_min: float | None
    time_to_close_median_min: float | None
    time_to_close_avg_min: float | None


class FaqHealth(ApiModel):
    faq_item_id: int
    title: str
    used: int
    resolved: int
    resolved_share: float | None


class AgentHealth(ApiModel):
    classified: int
    corrected: int
    corrected_share: float | None
    other_share: float | None


class Indicators(ApiModel):
    volume: Volume
    outcomes: Outcomes
    heatmap: Heatmap
    time: TimeStats
    faq_health: list[FaqHealth]
    agent_health: AgentHealth


class IndicatorsQueryOut(ApiModel):
    from_date: str
    to_date: str
    unit_id: int | None
    normalize: bool


class IndicatorsResponse(ApiModel):
    query: IndicatorsQueryOut
    units: list[IdName]
    data: Indicators


# Requests


class LoginIn(ApiModel):
    user: StrictStr
    password: StrictStr


class MeOut(ApiModel):
    user: str


class MoveIn(ApiModel):
    to: BoardColumn


class TakeIn(ApiModel):
    responsible_id: JsonInt | None


class CategoryIn(ApiModel):
    category_id: JsonInt


class HealthOut(ApiModel):
    ok: bool


class ErrorOut(ApiModel):
    detail: str
