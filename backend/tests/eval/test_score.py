from typing import Any

import pytest

from geniai.domain.types import InterpretedTurn
from geniai.eval.cases import EvalCase, Expected, FaqFeedbackCase, FaqQuestionCase, ImageCase, build_catalog
from geniai.eval.score import (
    CaseRun,
    percentile,
    score_faq_feedback,
    score_faq_questions,
    score_images,
    score_runs,
)

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


def test_scores_questions_on_the_feedback_whether_the_answer_was_found_and_the_reply() -> None:
    cases = [
        FaqQuestionCase("q1", "password", "vale por quanto tempo?", True),
        FaqQuestionCase("q2", "password", "troco o e-mail?", False),
        FaqQuestionCase("q3", "report", "exporta em PDF?", False),
        FaqQuestionCase("q4", "report", "demora quanto?", True),
    ]
    runs = [
        CaseRun("q1", 1, turn(faq_feedback="question", faq_answer_found=True, reply="Vale 1 hora.")),
        CaseRun("q2", 1, turn(faq_feedback="question", faq_answer_found=False, reply="")),
        CaseRun("q3", 1, turn(faq_feedback="question", faq_answer_found=True, reply="Exporta sim.")),
        CaseRun("q4", 1, None, "timeout"),
    ]
    assert score_faq_questions(cases, runs) == pytest.approx(2 / 4)
    assert score_faq_questions([], []) == 1


def test_scores_images_on_the_category_the_faq_entry_and_a_description() -> None:
    login, password = id_of("Painel / Não consegue entrar"), faq_of("Redefinir senha do painel")
    cases = [
        ImageCase("i1", "a.png", Expected(False, "Painel / Não consegue entrar", "Redefinir senha do painel")),
        ImageCase("i2", "b.png", Expected(False, "Painel / Não consegue entrar", "Redefinir senha do painel")),
        ImageCase("i3", "c.png", Expected(False, "Painel / Não consegue entrar", "Redefinir senha do painel")),
        ImageCase("i4", "d.png", Expected(False, "Geral / Outros", None)),
    ]
    runs = [
        CaseRun("i1", 1, turn(category_id=login, faq_item_id=password, image_descriptions=("Erro de senha.",))),
        CaseRun("i2", 1, turn(category_id=login, faq_item_id=password)),
        CaseRun("i3", 1, turn(category_id=login, faq_item_id=None, image_descriptions=("Erro.",))),
        CaseRun("i4", 1, None, "timeout"),
    ]
    assert score_images(cases, runs, CATALOG) == pytest.approx(1 / 4)
    assert score_images([], [], CATALOG) == 1


def test_scores_clarification_on_cases_without_a_human_request_counting_failures_as_wrong() -> None:
    other = "Geral / Outros"
    cases = [
        EvalCase("v1", ["preciso de ajuda"], Expected(False, other, None, clarifies=True)),
        EvalCase("v2", ["tá dando erro"], Expected(False, other, None, clarifies=True)),
        EvalCase("r1", ["relatório financeiro"], Expected(False, other, None)),
        EvalCase("r2", ["link da reunião"], Expected(False, other, None)),
        EvalCase("r3", ["cancelar"], Expected(False, other, None)),
        EvalCase("h", ["quero um atendente"], Expected(True, other, None)),
    ]
    runs = [
        CaseRun("v1", 1, turn(needs_clarification=True)),
        CaseRun("v2", 1, turn(needs_clarification=True, faq_item_id=faq_of("Redefinir senha do painel"))),
        CaseRun("r1", 1, turn()),
        CaseRun("r2", 1, turn(needs_clarification=True)),
        CaseRun("r3", 1, None, "timeout"),
        CaseRun("h", 1, turn(human_requested=True, needs_clarification=True)),
    ]
    report = score_runs("m", cases, runs, CATALOG)
    # v1 and r1 are right; v2 sent an entry instead of asking, r2 asked, r3 failed; h is not counted.
    assert report.clarification_accuracy == pytest.approx(2 / 5)


def test_scores_faq_feedback_on_the_feedback_counting_failures_as_wrong() -> None:
    cases = [
        FaqFeedbackCase("f1", "password", "não é isso", "not_resolved"),
        FaqFeedbackCase("f2", "report", "não tem nada a ver", "not_resolved"),
        FaqFeedbackCase("f3", "reconnect", "não era isso", "not_resolved"),
        FaqFeedbackCase("f4", "password", "deu certo", "resolved"),
    ]
    runs = [
        CaseRun("f1", 1, turn(faq_feedback="not_resolved")),
        CaseRun("f2", 1, turn(faq_feedback="unclear")),
        CaseRun("f3", 1, None, "timeout"),
        CaseRun("f4", 1, turn(faq_feedback="resolved")),
    ]
    assert score_faq_feedback(cases, runs) == pytest.approx(2 / 4)
    assert score_faq_feedback([], []) == 1


def test_a_report_has_no_faq_feedback_accuracy_until_it_runs() -> None:
    assert REPORT.faq_feedback_accuracy is None
