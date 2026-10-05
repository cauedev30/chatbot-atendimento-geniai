"""The LLM contract (spec §6). Categories and FAQ ids come from the database:
an unknown category is rejected, an unknown FAQ id becomes None. There is no action field.
"""

from collections.abc import Collection
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from geniai.domain.attachments import MAX_DESCRIPTION_LEN
from geniai.domain.types import FaqFeedback, InterpretedTurn
from geniai.json_types import JsonInt

MAX_HANDOFF_REPLY_LEN = 300
"""A longer handoff reply is not a short sentence: the code's fixed text goes instead."""


class _TurnOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    human_requested: StrictBool
    registration_mismatch: StrictBool
    off_topic: StrictBool
    category_id: JsonInt
    faq_item_id: JsonInt | None
    faq_feedback: FaqFeedback | None
    needs_clarification: StrictBool
    summary: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    reply: Annotated[StrictStr, Field(max_length=1000)]
    faq_answer_found: StrictBool = False
    image_descriptions: object = None
    """Read leniently (see _descriptions): a bad value here never costs the turn."""
    handoff_reply: object = None
    """Read leniently (see _handoff_reply), like image_descriptions."""


def _descriptions(raw: object) -> tuple[str, ...]:
    """Keeps the position of each entry, so the n-th description stays with the n-th image."""
    if not isinstance(raw, list):
        return ()
    return tuple(item.strip()[:MAX_DESCRIPTION_LEN] if isinstance(item, str) else "" for item in raw)


def _handoff_reply(raw: object) -> str:
    """The sentence the LLM wrote for a handoff; "" when absent, not text or too long."""
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    return text if len(text) <= MAX_HANDOFF_REPLY_LEN else ""


def parse_turn_output(raw: object, category_ids: Collection[int], faq_item_ids: Collection[int]) -> InterpretedTurn:
    """Validates a raw (already JSON-decoded) LLM output. Raises ValueError when it is invalid."""
    out = _TurnOutput.model_validate(raw)
    if out.category_id not in category_ids:
        raise ValueError(f"category_id {out.category_id}: category not in the active list")
    faq_item_id = out.faq_item_id if out.faq_item_id is not None and out.faq_item_id in faq_item_ids else None
    return InterpretedTurn(
        human_requested=out.human_requested,
        registration_mismatch=out.registration_mismatch,
        off_topic=out.off_topic,
        category_id=out.category_id,
        faq_item_id=faq_item_id,
        faq_feedback=out.faq_feedback,
        needs_clarification=out.needs_clarification,
        summary=out.summary,
        reply=out.reply,
        faq_answer_found=out.faq_answer_found,
        image_descriptions=_descriptions(out.image_descriptions),
        handoff_reply=_handoff_reply(out.handoff_reply),
    )
