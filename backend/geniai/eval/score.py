import math
from dataclasses import dataclass

from geniai.domain.human_request import mentions_human_request
from geniai.domain.types import InterpretedTurn
from geniai.eval.cases import EvalCase, EvalCatalog


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
    latency_p50_ms: int | None
    latency_p95_ms: int | None


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


def score_runs(label: str, cases: list[EvalCase], runs: list[CaseRun], catalog: EvalCatalog) -> ModelReport:
    category_ids = {c.label: c.id for c in catalog.categories}
    faq_ids = {f.title: f.id for f in catalog.faq_items}
    turns = {r.case_id: r.turn for r in reversed(runs)}  # first run of a case wins, like Array.find
    expected = by_model_hits = with_keywords_hits = fp_model = fp_keywords = 0
    category_hits = faq_cases = faq_hits = failures = 0

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
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
    )
