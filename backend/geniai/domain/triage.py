from dataclasses import dataclass

from geniai.domain.rules import TriageRules
from geniai.domain.types import (
    AnswerFaqQuestion,
    AskClarification,
    AskForText,
    Decision,
    Handoff,
    InterpretedTurn,
    ReaskFeedback,
    ResolvedByBot,
    SendFaq,
    TriageState,
    UnreadMedia,
)


@dataclass(frozen=True)
class PreLlmSignals:
    keyword_human_request: bool
    """Result of mentions_human_request() on the turn's text."""
    nothing_legible: bool
    """The turn has attachments and nothing the LLM can read: no text and no image that opened."""
    unread: UnreadMedia = "media"
    """With nothing_legible: what the bot could not read, which picks the reply."""


def pre_llm_decision(state: TriageState, signals: PreLlmSignals, rules: TriageRules) -> Decision | None:
    """Rules decided in code before calling the LLM. None means: call the LLM."""
    if signals.keyword_human_request:
        return Handoff("human_requested")
    if signals.nothing_legible:
        # OWNER-UNCONFIRMED: media asks for text max_media_prompts times, then hands over.
        return AskForText(signals.unread) if state.media_prompts < rules.max_media_prompts else Handoff("media")
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
        if turn.faq_feedback == "new_problem":
            # Another problem than the entry sent: its own entry, when there is one (owner, 2026-10-05).
            if turn.faq_item_id is not None and turn.faq_item_id != state.sent_faq_item_id:
                return SendFaq(turn.faq_item_id)
            return Handoff("no_faq_match")
        if turn.faq_feedback == "resolved":
            return ResolvedByBot()
        if turn.faq_feedback == "not_resolved":
            return Handoff("faq_not_resolved")
        if turn.faq_feedback == "question":
            # Answered only from the knowledge base of the entry sent, max_faq_questions times.
            answered = turn.faq_answer_found and turn.reply.strip() != ""
            if answered and state.faq_questions_answered < rules.max_faq_questions:
                return AnswerFaqQuestion()
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


def handoff_text(turn: InterpretedTurn | None, fallback: str) -> str:
    """The sentence for a handoff: the LLM's, only when its own reading hands the customer over (the cases
    the prompt gives it); otherwise, e.g. at a limit only the code knows, or when it wrote none, `fallback`."""
    if turn is None:
        return fallback
    reads_as_handoff = (
        turn.human_requested
        or turn.registration_mismatch
        or turn.off_topic
        or turn.faq_feedback in ("not_resolved", "unclear")
        or (turn.faq_feedback == "question" and not turn.faq_answer_found)
        or (turn.faq_feedback == "new_problem" and turn.faq_item_id is None)
        or (turn.faq_feedback is None and turn.faq_item_id is None and not turn.needs_clarification)
    )
    return (turn.handoff_reply.strip() if reads_as_handoff else "") or fallback
