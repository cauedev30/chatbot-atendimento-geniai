"""Runs the evaluation set against every candidate in EVAL_CANDIDATES (spec §11, decision 8).
Each candidate names the env variable that holds its key; keys never appear in files.

    python -m geniai.eval.run
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, Field, TypeAdapter, ValidationError

from geniai.domain.rules import DEFAULT_RULES
from geniai.eval.cases import CASES, build_catalog, context_for
from geniai.eval.score import CaseRun, ModelReport, score_runs
from geniai.llm.interpret import interpret_turn
from geniai.llm.openai_compatible import OpenAiCompatibleConfig, create_openai_compatible_llm

NonEmpty = Annotated[str, Field(min_length=1)]


class Candidate(BaseModel):
    label: NonEmpty
    baseUrl: AnyHttpUrl
    model: NonEmpty
    apiKeyEnv: NonEmpty
    extraBody: dict[str, object] | None = None


_CANDIDATES: TypeAdapter[list[Candidate]] = TypeAdapter(Annotated[list[Candidate], Field(min_length=1)])

# Generous timeout and no retry: we measure the model, not the production guard rails.
EVAL_RULES = replace(DEFAULT_RULES, llm_timeout_ms=30_000, llm_retries=0)


class EvalConfigError(Exception):
    pass


def load_candidates(env: dict[str, str] | os._Environ[str]) -> list[Candidate]:
    raw = env.get("EVAL_CANDIDATES", "").strip() or "[]"
    try:
        return _CANDIDATES.validate_python(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as err:
        raise EvalConfigError(
            "EVAL_CANDIDATES must be a non-empty JSON list of "
            '{"label", "baseUrl", "model", "apiKeyEnv", "extraBody"?} objects; see .env.example.'
        ) from err


async def run_candidate(candidate: Candidate, api_key: str) -> list[CaseRun]:
    llm = create_openai_compatible_llm(
        OpenAiCompatibleConfig(
            base_url=str(candidate.baseUrl), api_key=api_key, model=candidate.model, extra_body=candidate.extraBody
        )
    )
    catalog = build_catalog()
    runs: list[CaseRun] = []
    print(f"{candidate.label} ", end="", flush=True)
    for case in CASES:
        started = time.perf_counter()
        result = await interpret_turn(llm, context_for(case, catalog), EVAL_RULES)
        latency_ms = round((time.perf_counter() - started) * 1000)
        runs.append(CaseRun(case.id, latency_ms, result.turn, None if result.ok else result.error))
        print("." if result.ok else "x", end="", flush=True)
    print()
    return runs


def _pct(n: float) -> str:
    return f"{round(n * 100)}%"


def print_table(reports: list[ModelReport]) -> None:
    header = ["model", "human (model)", "human (model+keywords)", "gate", "false positives", "category", "faq"]
    header += ["p50 ms", "p95 ms", "failures"]
    rows = [
        [
            r.label,
            _pct(r.human_request.model_rate),
            _pct(r.human_request.system_rate),
            "PASS" if r.passes_human_request_gate else "FAIL",
            str(r.human_request.false_positives_model),
            _pct(r.category_accuracy),
            _pct(r.faq_accuracy),
            str(r.latency_p50_ms),
            str(r.latency_p95_ms),
            str(r.failures),
        ]
        for r in reports
    ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


async def evaluate(
    candidates: list[Candidate], keys: dict[str, str]
) -> tuple[list[ModelReport], dict[str, list[CaseRun]]]:
    catalog = build_catalog()
    reports: list[ModelReport] = []
    all_runs: dict[str, list[CaseRun]] = {}
    for candidate in candidates:
        runs = await run_candidate(candidate, keys[candidate.apiKeyEnv])
        all_runs[candidate.label] = runs
        reports.append(score_runs(candidate.label, CASES, runs, catalog))
    return reports, all_runs


def save_results(reports: list[ModelReport], all_runs: dict[str, list[CaseRun]]) -> Path:
    out_dir = Path("eval-results")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).isoformat().replace(":", "-").replace(".", "-")
    out = out_dir / f"{stamp}.json"
    payload = {
        "reports": [asdict(r) for r in reports],
        "runs": {k: [asdict(r) for r in v] for k, v in all_runs.items()},
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    try:
        candidates = load_candidates(os.environ)
    except EvalConfigError as err:
        print(err, file=sys.stderr)
        return 2
    keys: dict[str, str] = {}
    for candidate in candidates:
        api_key = os.environ.get(candidate.apiKeyEnv)
        if not api_key:
            print(f"{candidate.apiKeyEnv} is not set", file=sys.stderr)
            return 2
        keys[candidate.apiKeyEnv] = api_key
    reports, all_runs = asyncio.run(evaluate(candidates, keys))
    print_table(reports)
    print(f"Saved {save_results(reports, all_runs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
