import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import insert as sa_insert

from geniai.app.indicators import IndicatorFilter, compute_indicators, list_units
from geniai.db.schema import ticket
from tests.conftest import Harness

_conversations = itertools.count(1)


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)


def minutes_after(iso: str, minutes: int) -> datetime:
    return at(iso) + timedelta(minutes=minutes)


async def insert(h: Harness, **values: Any) -> None:
    row: dict[str, Any] = {
        "column": "awaiting_human",
        "chatwoot_conversation_id": next(_conversations),
        "attendant_id": h.seed.attendants["ana"].id,
        "unit_id": h.seed.units["centro"],
        "opened_at": at("2026-09-10T15:00:00Z"),
    }
    async with h.begin() as conn:
        await conn.execute(sa_insert(ticket).values(**(row | values)))


async def scenario(h: Harness) -> None:
    c = h.seed.categories
    norte = {"attendant_id": h.seed.attendants["carla"].id, "unit_id": h.seed.units["norte"]}
    password = h.seed.faq["password"]
    # t1: FAQ worked.
    await insert(
        h,
        column="resolved_by_bot",
        category_id=c["login"],
        bot_category_id=c["login"],
        faq_attempted=True,
        faq_item_id=password,
        opened_at=at("2026-09-10T15:00:00Z"),
        closed_at=minutes_after("2026-09-10T15:00:00Z", 10),
    )
    # t2: FAQ did not work, waiting.
    await insert(
        h,
        column="awaiting_human",
        category_id=c["login"],
        bot_category_id=c["login"],
        faq_attempted=True,
        faq_item_id=password,
        handoff_reason="faq_not_resolved",
        opened_at=at("2026-09-11T14:50:00Z"),
        handed_off_at=at("2026-09-11T15:00:00Z"),
    )
    # t3: in progress, category corrected by a human (agent said "Outros").
    await insert(
        h,
        **norte,
        column="in_progress",
        category_id=c["report"],
        bot_category_id=c["other"],
        handoff_reason="no_faq_match",
        opened_at=at("2026-09-15T09:55:00Z"),
        handed_off_at=at("2026-09-15T10:00:00Z"),
        taken_at=at("2026-09-15T10:30:00Z"),
    )
    # t4: resolved by a human.
    await insert(
        h,
        **norte,
        column="resolved_by_human",
        category_id=c["report"],
        bot_category_id=c["report"],
        handoff_reason="no_faq_match",
        opened_at=at("2026-09-16T12:00:00Z"),
        handed_off_at=at("2026-09-16T12:05:00Z"),
        taken_at=at("2026-09-16T12:15:00Z"),
        closed_at=at("2026-09-16T13:00:00Z"),
    )
    # t5: customer vanished.
    await insert(
        h,
        column="no_response",
        category_id=c["schedule"],
        bot_category_id=c["schedule"],
        opened_at=at("2026-09-20T12:00:00Z"),
        closed_at=at("2026-09-21T12:00:00Z"),
    )
    # t6: unknown number.
    await insert(
        h,
        attendant_id=None,
        unit_id=None,
        column="awaiting_human",
        category_id=c["unidentified"],
        handoff_reason="unidentified",
        opened_at=at("2026-09-12T15:00:00Z"),
        handed_off_at=at("2026-09-12T15:00:00Z"),
    )
    # t7: still with the bot.
    await insert(h, column="in_triage", opened_at=at("2026-09-22T15:00:00Z"))
    # t8: outside the period.
    await insert(
        h,
        column="resolved_by_bot",
        category_id=c["login"],
        bot_category_id=c["login"],
        opened_at=at("2026-08-15T15:00:00Z"),
        closed_at=at("2026-08-15T15:05:00Z"),
    )


def september(unit_id: int | None = None) -> IndicatorFilter:
    return IndicatorFilter(from_=at("2026-09-01T03:00:00Z"), to=at("2026-10-01T03:00:00Z"), unit_id=unit_id)


async def test_counts_volume_by_week_sao_paulo_time_month_unit_and_category(h: Harness) -> None:
    await scenario(h)
    volume = (await compute_indicators(h.deps, september())).volume
    assert volume.total == 7
    assert [(w.period, w.count) for w in volume.by_week] == [("2026-09-07", 3), ("2026-09-14", 3), ("2026-09-21", 1)]
    assert [(m.period, m.count) for m in volume.by_month] == [("2026-09", 7)]
    by_unit = {u.unit_name: u.count for u in volume.by_unit}
    assert by_unit["Unidade Exemplo Centro"] == 4
    assert by_unit["Unidade Exemplo Norte"] == 2
    by_category = {c.label: c.count for c in volume.by_category}
    assert by_category["Painel / Relatório não carrega"] == 2


async def test_reports_outcomes_and_the_bot_resolution_rate_without_counting_no_response_as_success(
    h: Harness,
) -> None:
    await scenario(h)
    outcomes = (await compute_indicators(h.deps, september())).outcomes
    assert outcomes.by_column == {
        "resolved_by_bot": 1,
        "awaiting_human": 2,
        "in_progress": 1,
        "resolved_by_human": 1,
        "no_response": 1,
    }
    assert sorted((r.reason, r.count) for r in outcomes.by_handoff_reason) == [
        ("faq_not_resolved", 1),
        ("no_faq_match", 2),
        ("unidentified", 1),
    ]
    assert outcomes.identified_reached == 5
    assert outcomes.bot_resolution_rate == pytest.approx(0.2)
    assert outcomes.no_response_share == pytest.approx(0.2)


async def test_builds_the_unit_by_category_heatmap_with_active_attendant_counts(h: Harness) -> None:
    await scenario(h)
    heatmap = (await compute_indicators(h.deps, september())).heatmap
    assert [(u.id, u.name, u.attendants) for u in heatmap.units] == [
        (h.seed.units["centro"], "Unidade Exemplo Centro", 2),
        (h.seed.units["norte"], "Unidade Exemplo Norte", 1),
    ]
    cells = {(c.unit_id, c.category_id, c.count) for c in heatmap.cells}
    assert (h.seed.units["centro"], h.seed.categories["login"], 2) in cells
    assert (h.seed.units["norte"], h.seed.categories["report"], 2) in cells


async def test_measures_waiting_and_closing_times_in_minutes(h: Harness) -> None:
    await scenario(h)
    time = (await compute_indicators(h.deps, september())).time
    assert time.wait_to_take_median_min == pytest.approx(20)
    assert time.wait_to_take_avg_min == pytest.approx(20)
    assert time.time_to_close_median_min == pytest.approx(60)
    assert time.time_to_close_avg_min == pytest.approx((10 + 60 + 1440) / 3)


async def test_reports_faq_and_agent_health(h: Harness) -> None:
    await scenario(h)
    result = await compute_indicators(h.deps, september())
    faq = {f.faq_item_id: f for f in result.faq_health}
    password = faq[h.seed.faq["password"]]
    assert (password.used, password.resolved, password.resolved_share) == (2, 1, 0.5)
    report = faq[h.seed.faq["report"]]
    assert (report.used, report.resolved_share) == (0, None)
    agent = result.agent_health
    assert (agent.classified, agent.corrected) == (5, 1)
    assert agent.corrected_share == pytest.approx(0.2)
    assert agent.other_share == pytest.approx(0.2)


async def test_filters_by_unit(h: Harness) -> None:
    await scenario(h)
    r = await compute_indicators(h.deps, september(h.seed.units["norte"]))
    assert r.volume.total == 2
    assert r.outcomes.bot_resolution_rate == 0
    assert [u.id for u in r.heatmap.units] == [h.seed.units["norte"]]


async def test_returns_empty_values_for_an_empty_period(h: Harness) -> None:
    r = await compute_indicators(h.deps, september())
    assert r.volume.total == 0
    assert r.outcomes.bot_resolution_rate is None
    assert r.time.wait_to_take_median_min is None


async def test_lists_active_units_by_name(h: Harness) -> None:
    assert [u.name for u in await list_units(h.deps)] == ["Unidade Exemplo Centro", "Unidade Exemplo Norte"]
