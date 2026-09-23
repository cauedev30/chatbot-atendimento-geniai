from dataclasses import dataclass
from typing import ClassVar, Final, Literal, get_args

Column = Literal[
    "in_triage",
    "resolved_by_bot",
    "awaiting_human",
    "in_progress",
    "resolved_by_human",
    "no_response",
]
COLUMNS: Final[tuple[Column, ...]] = get_args(Column)

BoardColumn = Literal[
    "resolved_by_bot",
    "awaiting_human",
    "in_progress",
    "resolved_by_human",
    "no_response",
]
"""Kanban columns in display order (spec §5.2). "in_triage" is shown as a counter, not a column."""
BOARD_COLUMNS: Final[tuple[BoardColumn, ...]] = get_args(BoardColumn)

CLOSED_COLUMNS: Final[tuple[Column, ...]] = ("resolved_by_bot", "resolved_by_human", "no_response")


def is_closed(column: Column) -> bool:
    return column in CLOSED_COLUMNS


HandoffReason = Literal[
    "human_requested",
    "faq_not_resolved",
    "no_faq_match",
    "unidentified",
    "registration_mismatch",
    "off_topic",
    "media",
    "llm_failure",
]
HANDOFF_REASONS: Final[tuple[HandoffReason, ...]] = get_args(HandoffReason)

Actor = Literal["bot", "human"]
MessageAuthor = Literal["customer", "bot"]
FaqFeedback = Literal["resolved", "not_resolved", "unclear"]


@dataclass(frozen=True)
class InterpretedTurn:
    """The LLM output (spec §6) after validation, in code naming."""

    human_requested: bool
    registration_mismatch: bool
    off_topic: bool
    category_id: int
    faq_item_id: int | None
    faq_feedback: FaqFeedback | None
    needs_clarification: bool
    summary: str
    reply: str


@dataclass(frozen=True)
class TriageState:
    """Counters of a ticket in triage. `faq_attempted` true means the bot is awaiting FAQ feedback."""

    faq_attempted: bool
    clarifications_asked: int
    unclear_feedback_reasks: int
    media_prompts: int


@dataclass(frozen=True)
class Handoff:
    kind: ClassVar[Literal["handoff"]] = "handoff"
    reason: HandoffReason


@dataclass(frozen=True)
class SendFaq:
    kind: ClassVar[Literal["send_faq"]] = "send_faq"
    faq_item_id: int


@dataclass(frozen=True)
class AskClarification:
    kind: ClassVar[Literal["ask_clarification"]] = "ask_clarification"


@dataclass(frozen=True)
class ReaskFeedback:
    kind: ClassVar[Literal["reask_feedback"]] = "reask_feedback"


@dataclass(frozen=True)
class ResolvedByBot:
    kind: ClassVar[Literal["resolved_by_bot"]] = "resolved_by_bot"


@dataclass(frozen=True)
class AskForText:
    kind: ClassVar[Literal["ask_for_text"]] = "ask_for_text"


Decision = Handoff | SendFaq | AskClarification | ReaskFeedback | ResolvedByBot | AskForText
DecisionKind = Literal["handoff", "send_faq", "ask_clarification", "reask_feedback", "resolved_by_bot", "ask_for_text"]
