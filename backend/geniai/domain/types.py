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
FaqFeedback = Literal["resolved", "not_resolved", "question", "unclear"]


AttachmentKind = Literal["image", "audio", "video", "file"]
ATTACHMENT_KINDS: Final[tuple[AttachmentKind, ...]] = get_args(AttachmentKind)

ImageOutcome = Literal["seen", "failed", "over_limit"]
"""What became of an image once an LLM turn read its message: the LLM saw it, it did not open, or it was
past the per-turn limit. None until then."""
IMAGE_OUTCOMES: Final[tuple[ImageOutcome, ...]] = get_args(ImageOutcome)


@dataclass(frozen=True)
class Attachment:
    """A file sent with a customer message. `url` is Chatwoot's link to it, when there is one."""

    kind: AttachmentKind
    url: str | None = None
    outcome: ImageOutcome | None = None
    description: str | None = None
    """With outcome "seen": the LLM's short description of the image, shown in later turns instead of it."""


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
    faq_answer_found: bool = False
    """With faq_feedback "question": the answer is in the knowledge base of the FAQ entry sent."""
    image_descriptions: tuple[str, ...] = ()
    """A short description of each image sent with the turn, in order, as the LLM gave them ("" when an
    entry was not text); may be shorter or longer than the images sent."""


@dataclass(frozen=True)
class TriageState:
    """Counters of a ticket in triage. `faq_attempted` true means the bot is awaiting FAQ feedback."""

    faq_attempted: bool
    clarifications_asked: int
    unclear_feedback_reasks: int
    media_prompts: int
    faq_questions_answered: int


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


UnreadMedia = Literal["media", "image", "other"]
"""What a turn with nothing legible had: "media" when image reading is off (any attachment), "image" when
only images that did not open, "other" when an audio, a video or a file."""


@dataclass(frozen=True)
class AskForText:
    kind: ClassVar[Literal["ask_for_text"]] = "ask_for_text"
    unread: UnreadMedia = "media"


@dataclass(frozen=True)
class AnswerFaqQuestion:
    """Answer a question about the FAQ entry that was sent, with the LLM's reply drawn from its knowledge base."""

    kind: ClassVar[Literal["answer_faq_question"]] = "answer_faq_question"


Decision = Handoff | SendFaq | AskClarification | ReaskFeedback | ResolvedByBot | AskForText | AnswerFaqQuestion
DecisionKind = Literal[
    "handoff",
    "send_faq",
    "ask_clarification",
    "reask_feedback",
    "resolved_by_bot",
    "ask_for_text",
    "answer_faq_question",
]
