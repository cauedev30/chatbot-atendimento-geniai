from dataclasses import replace
from typing import Any

from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.triage import PreLlmSignals, decide_turn, pre_llm_decision
from geniai.domain.types import (
    AskClarification,
    AskForText,
    Handoff,
    InterpretedTurn,
    ReaskFeedback,
    ResolvedByBot,
    SendFaq,
    TriageState,
)


def state(**overrides: Any) -> TriageState:
    base: dict[str, Any] = {
        "faq_attempted": False,
        "clarifications_asked": 0,
        "unclear_feedback_reasks": 0,
        "media_prompts": 0,
    }
    return TriageState(**(base | overrides))


def turn(**overrides: Any) -> InterpretedTurn:
    base: dict[str, Any] = {
        "human_requested": False,
        "registration_mismatch": False,
        "off_topic": False,
        "category_id": 1,
        "faq_item_id": None,
        "faq_feedback": None,
        "needs_clarification": False,
        "summary": "resumo",
        "reply": "",
    }
    return InterpretedTurn(**(base | overrides))


# preLlmDecision


def test_hands_over_on_a_human_request_keyword_even_with_media() -> None:
    signals = PreLlmSignals(keyword_human_request=True, only_media=True)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) == Handoff("human_requested")


def test_asks_for_text_on_the_first_media_only_turn() -> None:
    signals = PreLlmSignals(keyword_human_request=False, only_media=True)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) == AskForText()


def test_hands_over_on_media_after_the_media_prompt_was_used() -> None:
    signals = PreLlmSignals(keyword_human_request=False, only_media=True)
    assert pre_llm_decision(state(media_prompts=1), signals, DEFAULT_RULES) == Handoff("media")


def test_returns_none_when_the_llm_must_be_called() -> None:
    signals = PreLlmSignals(keyword_human_request=False, only_media=False)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) is None


def test_follows_max_media_prompts() -> None:
    rules = replace(DEFAULT_RULES, max_media_prompts=0)
    signals = PreLlmSignals(keyword_human_request=False, only_media=True)
    assert pre_llm_decision(state(), signals, rules) == Handoff("media")


# decideTurn precedence (spec §5.3)


def test_1_human_request_beats_everything() -> None:
    t = turn(human_requested=True, registration_mismatch=True, off_topic=True, faq_item_id=3)
    assert decide_turn(state(), t, DEFAULT_RULES) == Handoff("human_requested")


def test_2_registration_mismatch_beats_off_topic_and_faq() -> None:
    t = turn(registration_mismatch=True, off_topic=True, faq_item_id=3)
    assert decide_turn(state(), t, DEFAULT_RULES) == Handoff("registration_mismatch")


def test_3_off_topic_beats_faq() -> None:
    assert decide_turn(state(), turn(off_topic=True, faq_item_id=3), DEFAULT_RULES) == Handoff("off_topic")


# 4. awaiting FAQ feedback

AWAITING = state(faq_attempted=True)


def test_4_resolved_closes_as_resolved_by_bot() -> None:
    assert decide_turn(AWAITING, turn(faq_feedback="resolved"), DEFAULT_RULES) == ResolvedByBot()


def test_4_not_resolved_hands_over() -> None:
    assert decide_turn(AWAITING, turn(faq_feedback="not_resolved"), DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_unclear_is_asked_again_once() -> None:
    assert decide_turn(AWAITING, turn(faq_feedback="unclear"), DEFAULT_RULES) == ReaskFeedback()


def test_4_null_feedback_counts_as_unclear() -> None:
    assert decide_turn(AWAITING, turn(faq_feedback=None), DEFAULT_RULES) == ReaskFeedback()


def test_4_a_second_unclear_answer_hands_over() -> None:
    again = state(faq_attempted=True, unclear_feedback_reasks=1)
    assert decide_turn(again, turn(faq_feedback="unclear"), DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_never_sends_a_second_faq_entry() -> None:
    t = turn(faq_feedback="not_resolved", faq_item_id=4)
    assert decide_turn(AWAITING, t, DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_follows_max_unclear_feedback_reasks() -> None:
    rules = replace(DEFAULT_RULES, max_unclear_feedback_reasks=0)
    assert decide_turn(AWAITING, turn(faq_feedback="unclear"), rules) == Handoff("faq_not_resolved")


def test_5_faq_match_sends_the_entry() -> None:
    assert decide_turn(state(), turn(faq_item_id=3, needs_clarification=True), DEFAULT_RULES) == SendFaq(3)


def test_6_asks_for_clarification_while_under_the_limit() -> None:
    result = decide_turn(state(clarifications_asked=1), turn(needs_clarification=True), DEFAULT_RULES)
    assert result == AskClarification()


def test_7_hands_over_when_the_clarification_limit_is_reached() -> None:
    result = decide_turn(state(clarifications_asked=2), turn(needs_clarification=True), DEFAULT_RULES)
    assert result == Handoff("no_faq_match")


def test_7_hands_over_with_no_faq_and_nothing_to_clarify() -> None:
    assert decide_turn(state(), turn(), DEFAULT_RULES) == Handoff("no_faq_match")


def test_decision_kinds_are_stable_names() -> None:
    kinds = [
        d.kind
        for d in (Handoff("media"), SendFaq(1), AskClarification(), ReaskFeedback(), ResolvedByBot(), AskForText())
    ]
    assert kinds == ["handoff", "send_faq", "ask_clarification", "reask_feedback", "resolved_by_bot", "ask_for_text"]
