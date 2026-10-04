import math
from dataclasses import dataclass

from geniai.domain.human_request import mentions_human_request
from geniai.domain.types import InterpretedTurn
from geniai.eval.cases import EvalCase, EvalCatalog, FaqFeedbackCase, FaqQuestionCase, ImageCase


@dataclass(frozen=True)
class CaseRun:
    case_id: str
    latency_ms: int
    turn: InterpretedTurn | None
    error: str | None = None


@dataclass(frozen=True)
class HumanRequestScore:
    expected: int
    detected_by_model: int
    detected_with_keywords: int
    false_positives_model: int
    false_positives_with_keywords: int
    model_rate: float
    system_rate: float


@dataclass(frozen=True)
class ModelReport:
    label: str
    cases: int
    failures: int
    human_request: HumanRequestScore
    passes_human_request_gate: bool
    """Spec §11: human-request detection must be 100%. Judged on the model alone, the stricter reading."""
    category_accuracy: float
    faq_accuracy: float
    clarification_accuracy: float
    """Among the cases with no human request, the share where the bot asked a question (no FAQ entry and
    needs_clarification) exactly when expected.clarifies. A failed run counts as wrong."""
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    faq_question_accuracy: float | None = None
    """Share of FAQ_QUESTION_CASES read right (see score_faq_questions); None when not run."""
    faq_feedback_accuracy: float | None = None
    """Share of FAQ_FEEDBACK_CASES with the expected faq_feedback (see score_faq_feedback); None when not run."""
    image_accuracy: float | None = None
    """Share of IMAGE_CASES read right (see score_images); None when the model does not read images."""


def percentile(values: list[int], p: float) -> int | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


_MISSING = -1
"""Id of a label absent from the catalog: never equal to a real id or to None."""


def _rate(n: int, d: int) -> float:
    return 1 if d == 0 else n / d


def score_faq_questions(cases: list[FaqQuestionCase], runs: list[CaseRun]) -> float:
    """A question is read right when the model says "question", finds the answer exactly when the knowledge
    base has it, and writes a reply exactly then. A failed run counts as wrong."""
    turns = {r.case_id: r.turn for r in reversed(runs)}
    hits = 0
    for c in cases:
        turn = turns.get(c.id)
        if turn is None or turn.faq_feedback != "question":
            continue
        if turn.faq_answer_found == c.answer_found and (turn.reply.strip() != "") == c.answer_found:
            hits += 1
    return _rate(hits, len(cases))


def score_faq_feedback(cases: list[FaqFeedbackCase], runs: list[CaseRun]) -> float:
    """An answer to the FAQ entry sent is read right when faq_feedback is the expected one. A failed run
    counts as wrong."""
    turns = {r.case_id: r.turn for r in reversed(runs)}
    hits = 0
    for c in cases:
        turn = turns.get(c.id)
        if turn is not None and turn.faq_feedback == c.feedback:
            hits += 1
    return _rate(hits, len(cases))


def score_images(cases: list[ImageCase], runs: list[CaseRun], catalog: EvalCatalog) -> float:
    """An image is read right when the category and the FAQ entry match and the model described it. A
    failed run counts as wrong."""
    category_ids = {c.label: c.id for c in catalog.categories}
    faq_ids = {f.title: f.id for f in catalog.faq_items}
    turns = {r.case_id: r.turn for r in reversed(runs)}
    hits = 0
    for c in cases:
        turn = turns.get(c.id)
        if turn is None or turn.category_id != category_ids.get(c.expected.category, _MISSING):
            continue
        expected_faq = None if c.expected.faq is None else faq_ids.get(c.expected.faq, _MISSING)
        if turn.faq_item_id == expected_faq and any(d != "" for d in turn.image_descriptions):
            hits += 1
    return _rate(hits, len(cases))


def score_runs(label: str, cases: list[EvalCase], runs: list[CaseRun], catalog: EvalCatalog) -> ModelReport:
    category_ids = {c.label: c.id for c in catalog.categories}
    faq_ids = {f.title: f.id for f in catalog.faq_items}
    turns = {r.case_id: r.turn for r in reversed(runs)}  # first run of a case wins, like Array.find
    expected = by_model_hits = with_keywords_hits = fp_model = fp_keywords = 0
    category_hits = faq_cases = faq_hits = clarification_hits = failures = 0

    for c in cases:
        turn = turns.get(c.id)
        if turn is None:
            failures += 1
        by_model = turn.human_requested if turn is not None else False
        by_system = by_model or mentions_human_request("\n".join(c.customer))
        if c.expected.human_requested:
            expected += 1
            by_model_hits += by_model
            with_keywords_hits += by_system
        else:
            fp_model += by_model
            fp_keywords += by_system
            faq_cases += 1
            expected_faq = None if c.expected.faq is None else faq_ids.get(c.expected.faq, _MISSING)
            if turn is not None and turn.faq_item_id == expected_faq:
                faq_hits += 1
            asked = turn is not None and turn.faq_item_id is None and turn.needs_clarification
            if turn is not None and asked == c.expected.clarifies:
                clarification_hits += 1
        if turn is not None and turn.category_id == category_ids.get(c.expected.category, _MISSING):
            category_hits += 1

    latencies = [r.latency_ms for r in runs if r.turn is not None]
    return ModelReport(
        label=label,
        cases=len(cases),
        failures=failures,
        human_request=HumanRequestScore(
            expected=expected,
            detected_by_model=by_model_hits,
            detected_with_keywords=with_keywords_hits,
            false_positives_model=fp_model,
            false_positives_with_keywords=fp_keywords,
            model_rate=_rate(by_model_hits, expected),
            system_rate=_rate(with_keywords_hits, expected),
        ),
        passes_human_request_gate=by_model_hits == expected,
        category_accuracy=_rate(category_hits, len(cases)),
        faq_accuracy=_rate(faq_hits, faq_cases),
        clarification_accuracy=_rate(clarification_hits, faq_cases),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
    )
