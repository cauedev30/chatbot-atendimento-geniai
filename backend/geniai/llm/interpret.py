import json
import re
import time
from dataclasses import dataclass
from typing import Literal

from geniai.app.ports import LlmPort, LlmRequest
from geniai.domain.rules import TriageRules
from geniai.domain.types import InterpretedTurn
from geniai.llm.output_schema import parse_turn_output
from geniai.llm.prompt import SYSTEM_PROMPT, TurnContext, build_user_payload

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


AttemptOutcome = Literal["ok", "timeout", "error", "invalid"]
"""How one LLM call ended: a valid turn, the time limit, a provider failure, or an output not valid."""


@dataclass(frozen=True)
class InterpretResult:
    ok: bool
    attempts: int
    turn: InterpretedTurn | None = None
    error: str = ""
    attempts_ms: tuple[int, ...] = ()
    """How long each call took, in order."""
    outcomes: tuple[AttemptOutcome, ...] = ()
    """How each call ended, in order."""


def _extract_json(raw: str) -> str:
    match = _JSON_OBJECT.search(raw)
    return match.group(0) if match else raw


async def interpret_turn(llm: LlmPort, ctx: TurnContext, rules: TriageRules) -> InterpretResult:
    """One LLM call per customer turn, validated; retried llm_retries times (spec §10)."""
    category_ids = {c.id for c in ctx.categories}
    faq_item_ids = {f.id for f in ctx.faq_items}
    timeout_ms = rules.llm_image_timeout_ms if ctx.images else rules.llm_timeout_ms
    request = LlmRequest(system=SYSTEM_PROMPT, user=build_user_payload(ctx), timeout_ms=timeout_ms, images=ctx.images)
    max_attempts = 1 + rules.llm_retries
    last_error = ""
    attempts_ms: list[int] = []
    outcomes: list[AttemptOutcome] = []

    def ended(outcome: AttemptOutcome, started: float) -> None:
        attempts_ms.append(round((time.perf_counter() - started) * 1000))
        outcomes.append(outcome)

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        try:
            content = await llm.complete(request)
        except Exception as err:
            last_error = str(err) or type(err).__name__
            ended("timeout" if isinstance(err, TimeoutError) else "error", started)
            continue
        try:
            raw = json.loads(_extract_json(content))
        except Exception as err:
            last_error = str(err) or type(err).__name__
            ended("invalid", started)
            continue
        try:
            turn = parse_turn_output(raw, category_ids, faq_item_ids)
        except ValueError as err:
            last_error = f"invalid output: {err}"
            ended("invalid", started)
            continue
        ended("ok", started)
        return InterpretResult(
            ok=True, attempts=attempt, turn=turn, attempts_ms=tuple(attempts_ms), outcomes=tuple(outcomes)
        )
    return InterpretResult(
        ok=False, attempts=max_attempts, error=last_error, attempts_ms=tuple(attempts_ms), outcomes=tuple(outcomes)
    )
