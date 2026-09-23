from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from geniai.domain.types import BOARD_COLUMNS, Actor, Column, is_closed

BOT_MOVES: Final[dict[Column, tuple[Column, ...]]] = {
    "in_triage": ("resolved_by_bot", "awaiting_human", "no_response"),
    "resolved_by_bot": (),
    "awaiting_human": (),
    "in_progress": (),
    "resolved_by_human": (),
    "no_response": (),
}
"""Moves the bot may make (spec §5.2). Humans may move a card to any board column."""


def can_move(from_: Column, to: Column, actor: Actor) -> bool:
    if from_ == to:
        return False
    if actor == "bot":
        return to in BOT_MOVES[from_]
    return to in BOARD_COLUMNS


@dataclass(frozen=True)
class TicketTimes:
    handed_off_at: datetime | None
    taken_at: datetime | None
    closed_at: datetime | None


def times_after_move(to: Column, now: datetime, current: TicketTimes) -> TicketTimes:
    """First handoff and first take are kept for the time indicators; closing is cleared on reopen."""
    return TicketTimes(
        handed_off_at=(current.handed_off_at or now) if to == "awaiting_human" else current.handed_off_at,
        taken_at=(current.taken_at or now) if to == "in_progress" else current.taken_at,
        closed_at=now if is_closed(to) else None,
    )


def chatwoot_status_after_move(from_: Column, to: Column) -> Literal["open", "resolved"] | None:
    """The Chatwoot conversation status to set after a move (spec §8, two-way sync):
    leaving the bot opens the conversation for the team, closing resolves it, reopening opens it.
    """
    if is_closed(to):
        return None if is_closed(from_) else "resolved"
    if is_closed(from_) or from_ == "in_triage":
        return "open"
    return None
