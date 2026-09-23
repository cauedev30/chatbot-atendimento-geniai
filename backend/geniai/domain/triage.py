from dataclasses import dataclass

from geniai.domain.rules import TriageRules
from geniai.domain.types import (
    AskClarification,
    AskForText,
    Decision,
    Handoff,
    InterpretedTurn,
    ReaskFeedback,
    ResolvedByBot,
    SendFaq,
    TriageState,
)


@dataclass(frozen=True)
class PreLlmSignals:
    keyword_human_request: bool
    """Result of mentions_human_request() on the turn's text."""
    only_media: bool
    """The turn has only media (audio, image, document) and no text."""


def pre_llm_decision(state: TriageState, signals: PreLlmSignals, rules: TriageRules) -> Decision | None:
    """Rules decided in code before calling the LLM. None means: call the LLM."""
    if signals.keyword_human_request:
        return Handoff("human_requested")
    if signals.only_media:
        # OWNER-UNCONFIRMED: media asks for text max_media_prompts times, then hands over.
        return AskForText() if state.media_prompts < rules.max_media_prompts else Handoff("media")
    return None


def decide_turn(state: TriageState, turn: InterpretedTurn, rules: TriageRules) -> Decision:
    """Spec §5.3: the first rule that applies wins."""
    if turn.human_requested:
        return Handoff("human_requested")
    if turn.registration_mismatch:
        return Handoff("registration_mismatch")
    if turn.off_topic:
        return Handoff("off_topic")
    if state.faq_attempted:
        if turn.faq_feedback == "resolved":
            return ResolvedByBot()
        if turn.faq_feedback == "not_resolved":
            return Handoff("faq_not_resolved")
        # OWNER-UNCONFIRMED: an unclear answer is asked again max_unclear_feedback_reasks times.
        if state.unclear_feedback_reasks < rules.max_unclear_feedback_reasks:
            return ReaskFeedback()
        return Handoff("faq_not_resolved")
    if turn.faq_item_id is not None:
        return SendFaq(turn.faq_item_id)
    if turn.needs_clarification and state.clarifications_asked < rules.max_clarifications:
        return AskClarification()
    return Handoff("no_faq_match")
