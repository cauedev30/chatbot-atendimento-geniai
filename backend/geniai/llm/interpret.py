import json
import re
from dataclasses import dataclass

from geniai.app.ports import LlmPort, LlmRequest
from geniai.domain.rules import TriageRules
from geniai.domain.types import InterpretedTurn
from geniai.llm.output_schema import parse_turn_output
from geniai.llm.prompt import SYSTEM_PROMPT, TurnContext, build_user_payload

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class InterpretResult:
    ok: bool
    attempts: int
    turn: InterpretedTurn | None = None
    error: str = ""


def _extract_json(raw: str) -> str:
    match = _JSON_OBJECT.search(raw)
    return match.group(0) if match else raw


async def interpret_turn(llm: LlmPort, ctx: TurnContext, rules: TriageRules) -> InterpretResult:
    """One LLM call per customer turn, validated; retried llm_retries times (spec §10)."""
    category_ids = {c.id for c in ctx.categories}
    faq_item_ids = {f.id for f in ctx.faq_items}
    request = LlmRequest(system=SYSTEM_PROMPT, user=build_user_payload(ctx), timeout_ms=rules.llm_timeout_ms)
    max_attempts = 1 + rules.llm_retries
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            raw = json.loads(_extract_json(await llm.complete(request)))
        except Exception as err:
            last_error = str(err) or type(err).__name__
            continue
        try:
            turn = parse_turn_output(raw, category_ids, faq_item_ids)
        except ValueError as err:
            last_error = f"invalid output: {err}"
            continue
        return InterpretResult(ok=True, attempts=attempt, turn=turn)
    return InterpretResult(ok=False, attempts=max_attempts, error=last_error)
