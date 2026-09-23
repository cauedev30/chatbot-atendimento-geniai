"""The LLM contract (spec §6). Categories and FAQ ids come from the database:
an unknown category is rejected, an unknown FAQ id becomes None. There is no action field.
"""

from collections.abc import Collection
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from geniai.domain.types import InterpretedTurn
from geniai.json_types import JsonInt


class _TurnOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    human_requested: StrictBool
    registration_mismatch: StrictBool
    off_topic: StrictBool
    category_id: JsonInt
    faq_item_id: JsonInt | None
    faq_feedback: Literal["resolved", "not_resolved", "unclear"] | None
    needs_clarification: StrictBool
    summary: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    reply: Annotated[StrictStr, Field(max_length=1000)]


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
    )
