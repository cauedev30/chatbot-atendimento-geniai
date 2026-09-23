from datetime import UTC, datetime

import pytest

from geniai.api.indicators import parse_indicators_query
from geniai.app.tickets_repo import NewTicket, create_ticket, move_ticket, update_ticket
from tests.api.conftest import Api

NOW = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)  # 12:00 in São Paulo


def test_defaults_to_the_last_30_days_in_sao_paulo() -> None:
    q = parse_indicators_query({}, NOW)
    assert q is not None
    assert (q.from_date, q.to_date, q.unit_id, q.normalize) == ("2026-08-25", "2026-09-23", None, False)
    assert q.filter.from_ == datetime(2026, 8, 25, 3, 0, tzinfo=UTC)
    assert q.filter.to == datetime(2026, 9, 24, 3, 0, tzinfo=UTC)


def test_uses_the_sao_paulo_date_late_in_the_evening() -> None:
    q = parse_indicators_query({}, datetime(2026, 9, 24, 2, 30, tzinfo=UTC))  # 23:30 on the 23rd in São Paulo
    assert q is not None
    assert q.to_date == "2026-09-23"


def test_reads_explicit_filters() -> None:
    q = parse_indicators_query({"from": "2026-09-01", "to": "2026-09-30", "unit": "3", "norm": "1"}, NOW)
    assert q is not None
    assert (q.unit_id, q.normalize) == (3, True)
    q = parse_indicators_query({"unit": "", "norm": "0"}, NOW)
    assert q is not None
    assert (q.unit_id, q.normalize) == (None, False)


@pytest.mark.parametrize(
    "params",
    [
        {"from": "01/09/2026"},
        {"from": "2026-09-30", "to": "2026-09-01"},
        {"from": "2026-13-01"},
        {"to": "2026-02-32"},
        {"unit": "abc"},
        {"unit": "0"},
        {"norm": "2"},
    ],
)
def test_rejects_bad_or_reversed_dates_and_bad_filters(params: dict[str, str]) -> None:
    assert parse_indicators_query(params, NOW) is None


def test_rolls_an_impossible_day_over_into_the_next_month() -> None:
    # "2026-02-30" is read as March 2, and the query keeps the text as typed.
    q = parse_indicators_query({"from": "2026-02-30", "to": "2026-03-10"}, NOW)
    assert q is not None
    assert q.from_date == "2026-02-30"
    assert q.filter.from_ == datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "params",
    [
        {"from": "1999-12-31", "to": "2000-01-10"},
        {"from": "2026-09-01", "to": "2101-01-01"},
        {"from": "0001-01-01", "to": "2026-09-01"},
        {"from": "2026-09-01", "to": "9999-12-31"},
    ],
)
def test_rejects_years_outside_2000_to_2100(params: dict[str, str]) -> None:
    assert parse_indicators_query(params, NOW) is None


async def test_an_absurd_date_is_a_400_not_a_500(logged_in: Api) -> None:
    res = await logged_in.client.get("/api/indicators?from=2026-09-01&to=9999-12-31")
    assert (res.status_code, res.json()) == (400, {"detail": "Período inválido."})


def test_uses_the_real_sao_paulo_time_zone_including_past_daylight_saving() -> None:
    # On 2018-11-05 São Paulo was on daylight saving time (UTC-2): midnight there is 02:00 UTC.
    q = parse_indicators_query({"from": "2018-11-05", "to": "2018-11-05"}, NOW)
    assert q is not None
    assert q.filter.from_ == datetime(2018, 11, 5, 2, 0, tzinfo=UTC)
    assert q.filter.to == datetime(2018, 11, 6, 2, 0, tzinfo=UTC)


async def two_tickets(api: Api) -> None:
    h = api.h
    ana = h.seed.attendants["ana"]
    login = h.seed.categories["login"]
    for conversation_id, to in [(1, "resolved_by_bot"), (2, "awaiting_human")]:
        async with h.begin() as conn:
            t = await create_ticket(
                conn,
                NewTicket(
                    column="in_triage",
                    conversation_id=conversation_id,
                    phone_e164=ana.phone,
                    attendant_id=ana.id,
                    unit_id=ana.unit_id,
                ),
                h.now,
            )
            await update_ticket(conn, t.id, {"category_id": login, "bot_category_id": login})
            patch: dict[str, object] = {"handoff_reason": "no_faq_match"} if to == "awaiting_human" else {}
            await move_ticket(conn, t.id, to, "bot", h.now, patch)  # type: ignore[arg-type]


async def test_requires_login(api: Api) -> None:
    assert (await api.client.get("/api/indicators")).status_code == 401


async def test_returns_the_six_blocks_with_the_bot_resolution_rate(logged_in: Api) -> None:
    await two_tickets(logged_in)
    res = await logged_in.client.get("/api/indicators")
    assert res.status_code == 200
    body = res.json()
    assert body["query"] == {"fromDate": "2026-08-25", "toDate": "2026-09-23", "unitId": None, "normalize": False}
    assert [u["name"] for u in body["units"]] == ["Unidade Exemplo Centro", "Unidade Exemplo Norte"]
    data = body["data"]
    assert list(data) == ["volume", "outcomes", "heatmap", "time", "faqHealth", "agentHealth"]
    assert data["outcomes"]["botResolutionRate"] == 0.5
    assert data["outcomes"]["byColumn"]["resolved_by_bot"] == 1
    assert data["outcomes"]["byHandoffReason"] == [{"reason": "no_faq_match", "count": 1}]
    assert data["volume"]["total"] == 2


async def test_passes_the_unit_and_normalization_through(logged_in: Api) -> None:
    await two_tickets(logged_in)
    centro = logged_in.h.seed.units["centro"]
    res = await logged_in.client.get(f"/api/indicators?from=2026-09-01&to=2026-09-30&unit={centro}&norm=1")
    body = res.json()
    assert body["query"] == {"fromDate": "2026-09-01", "toDate": "2026-09-30", "unitId": centro, "normalize": True}
    # Unidade Exemplo Centro has 2 active attendants and 2 tickets in "Painel / Não consegue entrar".
    [unit] = body["data"]["heatmap"]["units"]
    assert unit["attendants"] == 2
    [cell] = body["data"]["heatmap"]["cells"]
    assert cell["count"] / unit["attendants"] == 1


async def test_answers_400_to_an_invalid_period(logged_in: Api) -> None:
    res = await logged_in.client.get("/api/indicators?from=2026-09-30&to=2026-09-01")
    assert (res.status_code, res.json()) == (400, {"detail": "Período inválido."})
