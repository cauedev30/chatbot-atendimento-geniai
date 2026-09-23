from datetime import UTC, datetime

import pytest

from geniai.domain.transitions import TicketTimes, can_move, chatwoot_status_after_move, times_after_move
from geniai.domain.types import Column


@pytest.mark.parametrize(
    ("from_", "to"),
    [("in_triage", "resolved_by_bot"), ("in_triage", "awaiting_human"), ("in_triage", "no_response")],
)
def test_bot_may_move(from_: Column, to: Column) -> None:
    assert can_move(from_, to, "bot") is True


@pytest.mark.parametrize(
    ("from_", "to"),
    [
        ("in_triage", "in_progress"),
        ("awaiting_human", "in_progress"),
        ("resolved_by_bot", "awaiting_human"),
        ("awaiting_human", "no_response"),
    ],
)
def test_bot_may_not_move(from_: Column, to: Column) -> None:
    assert can_move(from_, to, "bot") is False


def test_humans_move_freely_between_board_columns() -> None:
    assert can_move("awaiting_human", "in_progress", "human") is True
    assert can_move("resolved_by_human", "awaiting_human", "human") is True
    assert can_move("no_response", "resolved_by_bot", "human") is True
    assert can_move("in_triage", "resolved_by_human", "human") is True


def test_nobody_moves_into_triage_or_onto_the_same_column() -> None:
    assert can_move("awaiting_human", "in_triage", "human") is False
    assert can_move("in_progress", "in_progress", "human") is False


T0 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 23, 13, 0, tzinfo=UTC)
EMPTY = TicketTimes(handed_off_at=None, taken_at=None, closed_at=None)


def test_stamps_the_first_handoff_and_keeps_it() -> None:
    first = times_after_move("awaiting_human", T0, EMPTY)
    assert first.handed_off_at == T0
    assert times_after_move("awaiting_human", T1, first).handed_off_at == T0


def test_stamps_the_first_take() -> None:
    current = TicketTimes(handed_off_at=T0, taken_at=None, closed_at=None)
    assert times_after_move("in_progress", T1, current).taken_at == T1


def test_stamps_closing_and_clears_it_on_reopen() -> None:
    closed = times_after_move("resolved_by_human", T0, EMPTY)
    assert closed.closed_at == T0
    assert times_after_move("awaiting_human", T1, closed).closed_at is None


@pytest.mark.parametrize(
    ("from_", "to", "expected"),
    [
        ("in_triage", "awaiting_human", "open"),
        ("in_triage", "resolved_by_bot", "resolved"),
        ("in_triage", "no_response", "resolved"),
        ("awaiting_human", "resolved_by_human", "resolved"),
        ("in_progress", "resolved_by_human", "resolved"),
        ("resolved_by_human", "awaiting_human", "open"),
        ("awaiting_human", "in_progress", None),
        ("resolved_by_bot", "resolved_by_human", None),
    ],
)
def test_chatwoot_status_after_move(from_: Column, to: Column, expected: str | None) -> None:
    assert chatwoot_status_after_move(from_, to) == expected
