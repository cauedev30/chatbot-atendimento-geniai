from dataclasses import replace
from typing import Any, get_args

import pytest

from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.triage import PreLlmSignals, decide_turn, handoff_text, pre_llm_decision
from geniai.domain.types import (
    AnswerFaqQuestion,
    AskClarification,
    AskForText,
    Handoff,
    InterpretedTurn,
    ReaskFeedback,
    ResolvedByBot,
    SendFaq,
    TriageState,
    UnreadMedia,
)


def state(**overrides: Any) -> TriageState:
    base: dict[str, Any] = {
        "faq_attempted": False,
        "clarifications_asked": 0,
        "unclear_feedback_reasks": 0,
        "media_prompts": 0,
        "faq_questions_answered": 0,
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
        "faq_answer_found": False,
    }
    return InterpretedTurn(**(base | overrides))


# preLlmDecision


def test_hands_over_on_a_human_request_keyword_even_with_media() -> None:
    signals = PreLlmSignals(keyword_human_request=True, nothing_legible=True)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) == Handoff("human_requested")


def test_asks_for_text_on_the_first_media_only_turn() -> None:
    signals = PreLlmSignals(keyword_human_request=False, nothing_legible=True)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) == AskForText()


def test_asks_for_text_naming_what_the_bot_could_not_read() -> None:
    for unread in get_args(UnreadMedia):
        signals = PreLlmSignals(keyword_human_request=False, nothing_legible=True, unread=unread)
        assert pre_llm_decision(state(), signals, DEFAULT_RULES) == AskForText(unread)


def test_hands_over_on_media_after_the_media_prompt_was_used() -> None:
    signals = PreLlmSignals(keyword_human_request=False, nothing_legible=True)
    assert pre_llm_decision(state(media_prompts=1), signals, DEFAULT_RULES) == Handoff("media")


def test_returns_none_when_the_llm_must_be_called() -> None:
    signals = PreLlmSignals(keyword_human_request=False, nothing_legible=False)
    assert pre_llm_decision(state(), signals, DEFAULT_RULES) is None


def test_follows_max_media_prompts() -> None:
    rules = replace(DEFAULT_RULES, max_media_prompts=0)
    signals = PreLlmSignals(keyword_human_request=False, nothing_legible=True)
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


# 4. a question about the FAQ entry that was sent


def question(**overrides: Any) -> InterpretedTurn:
    return turn(**({"faq_feedback": "question", "faq_answer_found": True, "reply": "Vale por 1 hora."} | overrides))


def test_4_a_question_answered_from_the_knowledge_base_is_answered() -> None:
    assert decide_turn(AWAITING, question(), DEFAULT_RULES) == AnswerFaqQuestion()


def test_4_the_third_question_is_still_answered() -> None:
    assert decide_turn(state(faq_attempted=True, faq_questions_answered=2), question(), DEFAULT_RULES) == (
        AnswerFaqQuestion()
    )


def test_4_the_fourth_question_hands_over() -> None:
    third_answered = state(faq_attempted=True, faq_questions_answered=3)
    assert decide_turn(third_answered, question(), DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_follows_max_faq_questions() -> None:
    assert DEFAULT_RULES.max_faq_questions == 3
    rules = replace(DEFAULT_RULES, max_faq_questions=0)
    assert decide_turn(AWAITING, question(), rules) == Handoff("faq_not_resolved")


def test_4_a_question_without_an_answer_in_the_knowledge_base_hands_over() -> None:
    assert decide_turn(AWAITING, question(faq_answer_found=False, reply=""), DEFAULT_RULES) == Handoff(
        "faq_not_resolved"
    )


def test_4_a_question_with_an_empty_reply_hands_over_even_if_the_answer_was_found() -> None:
    assert decide_turn(AWAITING, question(reply="  "), DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_a_question_does_not_use_the_unclear_answer_reask() -> None:
    reasked = state(faq_attempted=True, unclear_feedback_reasks=1)
    assert decide_turn(reasked, question(), DEFAULT_RULES) == AnswerFaqQuestion()


def test_4_resolved_and_not_resolved_come_before_a_question() -> None:
    assert decide_turn(AWAITING, question(faq_feedback="resolved"), DEFAULT_RULES) == ResolvedByBot()
    assert decide_turn(AWAITING, question(faq_feedback="not_resolved"), DEFAULT_RULES) == Handoff("faq_not_resolved")


def test_4_a_human_request_beats_a_question() -> None:
    assert decide_turn(AWAITING, question(human_requested=True), DEFAULT_RULES) == Handoff("human_requested")


def test_5_faq_match_sends_the_entry() -> None:
    assert decide_turn(state(), turn(faq_item_id=3, needs_clarification=True), DEFAULT_RULES) == SendFaq(3)


def test_6_asks_the_one_clarifying_question() -> None:
    result = decide_turn(state(clarifications_asked=0), turn(needs_clarification=True), DEFAULT_RULES)
    assert result == AskClarification()


def test_7_hands_over_instead_of_a_second_clarifying_question() -> None:
    # Owner, 2026-10-04: one question at most, then the support team.
    assert DEFAULT_RULES.max_clarifications == 1
    result = decide_turn(state(clarifications_asked=1), turn(needs_clarification=True), DEFAULT_RULES)
    assert result == Handoff("no_faq_match")


def test_7_hands_over_with_no_faq_and_nothing_to_clarify() -> None:
    assert decide_turn(state(), turn(), DEFAULT_RULES) == Handoff("no_faq_match")


def test_decision_kinds_are_stable_names() -> None:
    kinds = [
        d.kind
        for d in (
            Handoff("media"),
            SendFaq(1),
            AskClarification(),
            ReaskFeedback(),
            ResolvedByBot(),
            AskForText(),
            AnswerFaqQuestion(),
        )
    ]
    assert kinds == [
        "handoff",
        "send_faq",
        "ask_clarification",
        "reask_feedback",
        "resolved_by_bot",
        "ask_for_text",
        "answer_faq_question",
    ]


@pytest.mark.parametrize(
    "reading",
    [
        {"human_requested": True},
        {"registration_mismatch": True},
        {"off_topic": True},
        {"faq_feedback": "not_resolved"},
        {"faq_feedback": "unclear"},
        {"faq_feedback": "question", "faq_answer_found": False},
        {},
    ],
)
def test_a_handoff_the_llm_read_as_one_uses_its_sentence(reading: dict[str, Any]) -> None:
    assert handoff_text(turn(**reading, handoff_reply=" Vou te encaminhar. "), "fixo") == "Vou te encaminhar."
    assert handoff_text(turn(**reading), "fixo") == "fixo"


@pytest.mark.parametrize(
    "reading",
    [
        {"needs_clarification": True},
        {"faq_feedback": "question", "faq_answer_found": True, "reply": "Resposta."},
        {"faq_item_id": 10},
        {"faq_feedback": "resolved"},
    ],
)
def test_a_handoff_only_the_code_decided_keeps_the_fixed_text(reading: dict[str, Any]) -> None:
    assert handoff_text(turn(**reading, handoff_reply="Vou te encaminhar."), "fixo") == "fixo"


def test_a_handoff_without_the_llm_keeps_the_fixed_text() -> None:
    assert handoff_text(None, "fixo") == "fixo"
