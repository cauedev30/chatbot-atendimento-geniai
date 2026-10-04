from typing import Any

import pytest

from geniai.domain.types import InterpretedTurn
from geniai.eval import run
from geniai.eval.cases import CASES, FAQ_FEEDBACK_CASES, FAQ_QUESTION_CASES, build_catalog
from geniai.eval.run import Candidate, EvalConfigError, evaluate, load_candidates, print_table
from geniai.eval.score import CaseRun, score_runs


@pytest.mark.parametrize("raw", ["", "[]", "not json", '[{"label": "x"}]'])
def test_rejects_missing_or_invalid_candidates_with_a_clear_error(raw: str) -> None:
    with pytest.raises(EvalConfigError, match="EVAL_CANDIDATES"):
        load_candidates({"EVAL_CANDIDATES": raw})


def test_reads_the_documented_json_shape() -> None:
    raw = '[{"label":"candidate-a","baseUrl":"https://llm.example.com/v1","model":"model-a","apiKeyEnv":"KEY_A"}]'
    [candidate] = load_candidates({"EVAL_CANDIDATES": raw})
    assert (candidate.label, candidate.model, candidate.apiKeyEnv) == ("candidate-a", "model-a", "KEY_A")
    assert candidate.extraBody is None
    assert candidate.readsImages is False


def test_a_candidate_may_declare_that_it_reads_images() -> None:
    raw = '[{"label":"a","baseUrl":"https://llm.example.com/v1","model":"m","apiKeyEnv":"K","readsImages":true}]'
    [candidate] = load_candidates({"EVAL_CANDIDATES": raw})
    assert candidate.readsImages is True


def _turn(**overrides: Any) -> InterpretedTurn:
    fields: dict[str, Any] = {
        "human_requested": False,
        "registration_mismatch": False,
        "off_topic": False,
        "category_id": 100,
        "faq_item_id": None,
        "faq_feedback": None,
        "needs_clarification": False,
        "summary": "s",
        "reply": "",
    }
    return InterpretedTurn(**(fields | overrides))


async def test_evaluate_scores_the_faq_feedback_cases_apart_from_the_conversations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feedback = {c.id: c.feedback for c in FAQ_FEEDBACK_CASES}

    async def fake_run(candidate: Candidate, api_key: str) -> list[CaseRun]:
        runs = [CaseRun(c.id, 1, _turn(needs_clarification=c.expected.clarifies)) for c in CASES]
        runs += [CaseRun(c.id, 1, None, "timeout") for c in FAQ_QUESTION_CASES]
        # Every feedback case read right but the first.
        runs += [
            CaseRun(c.id, 1, _turn(faq_feedback="unclear" if i == 0 else feedback[c.id]))
            for i, c in enumerate(FAQ_FEEDBACK_CASES)
        ]
        return runs

    monkeypatch.setattr(run, "run_candidate", fake_run)
    candidate = Candidate.model_validate(
        {"label": "a", "baseUrl": "https://llm.example.com/v1", "model": "m", "apiKeyEnv": "K"}
    )
    [report], _ = await evaluate([candidate], {"K": "key"})
    assert (report.cases, report.failures) == (len(CASES), 0)
    assert report.clarification_accuracy == 1
    assert report.faq_feedback_accuracy == pytest.approx(3 / 4)
    assert report.faq_question_accuracy == 0


def test_the_table_has_the_clarify_and_faq_feedback_columns(capsys: pytest.CaptureFixture[str]) -> None:
    print_table([score_runs("a", [], [], build_catalog())])
    header = capsys.readouterr().out.splitlines()[0]
    assert "clarify" in header
    assert "faq feedback" in header
