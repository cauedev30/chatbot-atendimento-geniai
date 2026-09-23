import json

from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.types import TriageState
from geniai.llm.interpret import interpret_turn
from geniai.llm.prompt import PromptCategory, PromptFaqItem, PromptMessage, TurnContext, build_user_payload
from tests.support.fakes import ScriptedLlm, turn_json

CTX = TurnContext(
    attendant_name="Ana Exemplo",
    unit_name="Unidade Exemplo Centro",
    categories=[
        PromptCategory(id=1, system="Painel", name="Não consegue entrar"),
        PromptCategory(id=2, system="Geral", name="Outros"),
    ],
    faq_items=[
        PromptFaqItem(
            id=10, category_id=1, title="Redefinir senha do painel", applies_when="Não consegue entrar no painel."
        )
    ],
    messages=[
        PromptMessage(author="bot", text="Olá! Falo com Ana Exemplo?"),
        PromptMessage(author="customer", text="sim, não consigo entrar no painel"),
    ],
    state=TriageState(faq_attempted=False, clarifications_asked=0, unclear_feedback_reasks=0, media_prompts=0),
    max_clarifications=2,
)


async def test_returns_the_validated_turn_and_sends_the_context() -> None:
    llm = ScriptedLlm()
    llm.push(turn_json(category_id=1, faq_item_id=10))
    result = await interpret_turn(llm, CTX, DEFAULT_RULES)
    assert result.ok is True
    assert result.attempts == 1
    assert result.turn is not None
    assert (result.turn.category_id, result.turn.faq_item_id) == (1, 10)
    request = llm.requests[0]
    assert request.timeout_ms == DEFAULT_RULES.llm_timeout_ms
    assert "Ana Exemplo" in request.user
    assert "Unidade Exemplo Centro" in request.user
    assert "Não consegue entrar no painel." in request.user
    assert "answer_text" not in request.user


async def test_retries_once_after_invalid_json() -> None:
    llm = ScriptedLlm()
    llm.push("not json", turn_json(category_id=2))
    result = await interpret_turn(llm, CTX, DEFAULT_RULES)
    assert (result.ok, result.attempts) == (True, 2)


async def test_retries_once_after_a_provider_error() -> None:
    llm = ScriptedLlm()
    llm.push(TimeoutError("timeout"), turn_json(category_id=2))
    result = await interpret_turn(llm, CTX, DEFAULT_RULES)
    assert (result.ok, result.attempts) == (True, 2)


async def test_gives_up_after_the_retry() -> None:
    llm = ScriptedLlm()
    llm.push(TimeoutError("timeout"), turn_json(category_id=99))
    result = await interpret_turn(llm, CTX, DEFAULT_RULES)
    assert result.ok is False
    assert result.error
    assert len(llm.requests) == 2


async def test_accepts_json_inside_a_code_fence() -> None:
    llm = ScriptedLlm()
    llm.push("```json\n" + turn_json(category_id=1) + "\n```")
    assert (await interpret_turn(llm, CTX, DEFAULT_RULES)).ok is True


def test_the_user_payload_has_the_documented_shape() -> None:
    payload = build_user_payload(CTX)
    assert json.loads(payload) == {
        "registered": {"name": "Ana Exemplo", "unit": "Unidade Exemplo Centro"},
        "categories": [{"id": 1, "label": "Painel / Não consegue entrar"}, {"id": 2, "label": "Geral / Outros"}],
        "faq_items": [
            {
                "id": 10,
                "category_id": 1,
                "title": "Redefinir senha do painel",
                "applies_when": "Não consegue entrar no painel.",
            }
        ],
        "state": {"faq_attempted": False, "clarifications_asked": 0, "max_clarifications": 2},
        "conversation": [
            {"author": "bot", "text": "Olá! Falo com Ana Exemplo?"},
            {"author": "customer", "text": "sim, não consigo entrar no painel"},
        ],
    }
    # Accents kept, two-space indent, no trailing spaces.
    assert '  "registered": {\n    "name": "Ana Exemplo",' in payload
    assert " \n" not in payload
