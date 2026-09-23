from typing import Any

import pytest

from geniai.domain.types import InterpretedTurn
from geniai.eval.cases import EvalCase, Expected, build_catalog
from geniai.eval.score import CaseRun, percentile, score_runs

CATALOG = build_catalog()


def id_of(label: str) -> int:
    return next(c.id for c in CATALOG.categories if c.label == label)


def faq_of(title: str) -> int:
    return next(f.id for f in CATALOG.faq_items if f.title == title)


CASES = [
    EvalCase(
        "a",
        ["esqueci a senha do painel"],
        Expected(False, "Painel / Não consegue entrar", "Redefinir senha do painel"),
    ),
    EvalCase("b", ["não quero falar com robô"], Expected(True, "Geral / Outros", None)),
    EvalCase("c", ["quero falar com um atendente"], Expected(True, "Geral / Outros", None)),
    EvalCase("d", ["a pessoa do caixa não entra"], Expected(False, "Painel / Não consegue entrar", None)),
]


def turn(**overrides: Any) -> InterpretedTurn:
    fields: dict[str, Any] = {
        "human_requested": False,
        "registration_mismatch": False,
        "off_topic": False,
        "category_id": id_of("Geral / Outros"),
        "faq_item_id": None,
        "faq_feedback": None,
        "needs_clarification": False,
        "summary": "s",
        "reply": "",
    }
    return InterpretedTurn(**(fields | overrides))


RUNS = [
    CaseRun(
        "a",
        100,
        turn(category_id=id_of("Painel / Não consegue entrar"), faq_item_id=faq_of("Redefinir senha do painel")),
    ),
    CaseRun("b", 300, turn(human_requested=True)),
    CaseRun("c", 200, turn(human_requested=False)),
    CaseRun("d", 0, None, "timeout"),
]
REPORT = score_runs("model-x", CASES, RUNS, CATALOG)


def test_percentile_uses_the_nearest_rank() -> None:
    assert percentile([40, 10, 30, 20], 50) == 20
    assert percentile([40, 10, 30, 20], 95) == 40
    assert percentile([], 50) is None


def test_separates_the_models_detection_from_the_systems_model_plus_keywords() -> None:
    hr = REPORT.human_request
    assert (hr.expected, hr.detected_by_model, hr.detected_with_keywords) == (2, 1, 2)
    assert (hr.model_rate, hr.system_rate) == (0.5, 1)
    assert hr.false_positives_with_keywords == 1
    assert REPORT.passes_human_request_gate is False


def test_scores_category_and_faq_accuracy_counting_failures_as_wrong() -> None:
    assert REPORT.category_accuracy == pytest.approx(3 / 4)
    assert REPORT.faq_accuracy == pytest.approx(1 / 2)
    assert REPORT.failures == 1


def test_reports_latency_over_successful_runs() -> None:
    assert REPORT.latency_p50_ms == 200
    assert REPORT.latency_p95_ms == 300


def test_an_expected_faq_missing_from_the_catalog_never_counts_as_a_hit() -> None:
    cases = [EvalCase("x", ["?"], Expected(False, "Geral / Outros", "Não existe"))]
    report = score_runs("m", cases, [CaseRun("x", 1, turn(faq_item_id=None))], CATALOG)
    assert report.faq_accuracy == 0
