import json
from dataclasses import replace

from geniai.app.ports import ImageData
from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.types import TriageState
from geniai.llm.interpret import interpret_turn
from geniai.llm.prompt import (
    SYSTEM_PROMPT,
    PromptCategory,
    PromptFaqItem,
    PromptMessage,
    PromptSentFaq,
    TurnContext,
    build_user_payload,
)
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
    messages=[PromptMessage(author="bot", text="Olá! Falo com Ana Exemplo?")],
    new_messages=[PromptMessage(author="customer", text="sim, não consigo entrar no painel")],
    state=TriageState(
        faq_attempted=False,
        clarifications_asked=0,
        unclear_feedback_reasks=0,
        media_prompts=0,
        faq_questions_answered=0,
    ),
    max_clarifications=2,
    sent_faq=None,
    max_faq_questions=3,
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
        "state": {
            "faq_attempted": False,
            "clarifications_asked": 0,
            "max_clarifications": 2,
            "faq_questions_answered": 0,
            "max_faq_questions": 3,
        },
        "conversation": [{"author": "bot", "text": "Olá! Falo com Ana Exemplo?"}],
        "new_messages": ["sim, não consigo entrar no painel"],
    }
    # Accents kept, two-space indent, no trailing spaces.
    assert '  "registered": {\n    "name": "Ana Exemplo",' in payload
    assert " \n" not in payload


def test_after_the_faq_was_sent_the_payload_has_only_that_entry_with_its_text_and_knowledge_base() -> None:
    ctx = replace(
        CTX,
        state=replace(CTX.state, faq_attempted=True, faq_questions_answered=1),
        sent_faq=PromptSentFaq(
            id=10, title="Redefinir senha do painel", answer_text="1. Abra o login.", knowledge_base="- Vale 1 hora."
        ),
    )
    payload = json.loads(build_user_payload(ctx))
    assert payload["sent_faq"] == {
        "id": 10,
        "title": "Redefinir senha do painel",
        "answer_text": "1. Abra o login.",
        "knowledge_base": "- Vale 1 hora.",
    }
    assert payload["state"]["faq_attempted"] is True
    assert payload["state"]["faq_questions_answered"] == 1
    assert list(payload) == [
        "registered",
        "categories",
        "faq_items",
        "sent_faq",
        "state",
        "conversation",
        "new_messages",
    ]


def test_the_prompt_limits_answers_to_questions_to_the_entry_sent() -> None:
    assert '"question"' in SYSTEM_PROMPT
    assert "faq_answer_found" in SYSTEM_PROMPT
    assert "sent_faq.knowledge_base" in SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT
    assert "password" in SYSTEM_PROMPT


async def test_sends_the_images_of_the_turn_and_says_how_many_there_are() -> None:
    llm = ScriptedLlm()
    llm.push(turn_json(category_id=1, image_descriptions=["Tela de login com erro."]))
    image = ImageData(b"PNG-1", "image/png")
    ctx = replace(CTX, new_messages=[PromptMessage(author="customer", text="[imagem 1] deu isso")], images=(image,))
    result = await interpret_turn(llm, ctx, DEFAULT_RULES)
    assert result.turn is not None
    assert result.turn.image_descriptions == ("Tela de login com erro.",)
    assert llm.requests[0].images == (image,)
    payload = json.loads(llm.requests[0].user)
    assert (payload["images_attached"], payload["new_messages"]) == (1, ["[imagem 1] deu isso"])
    assert list(payload)[-2:] == ["new_messages", "images_attached"]


def test_a_turn_without_images_sends_no_image_count() -> None:
    assert "images_attached" not in json.loads(build_user_payload(CTX))


def test_the_prompt_explains_every_attachment_label_and_forbids_asking_to_resend() -> None:
    for label in [
        "[imagem 1]",
        "[imagem: ",
        "[imagem vista pelo bot]",
        "[imagem — não foi possível abrir]",
        "[imagem — além do limite, não vista]",
        "[áudio — o bot não ouve]",
        "[vídeo — o bot não abre]",
        "[arquivo — o bot não abre]",
    ]:
        assert label in SYSTEM_PROMPT
    assert "image_descriptions" in SYSTEM_PROMPT
    assert "resend" in SYSTEM_PROMPT
    assert "did not arrive" in SYSTEM_PROMPT


def test_a_text_turn_waits_5_s_for_the_llm_and_a_turn_with_images_8_s() -> None:
    assert (DEFAULT_RULES.llm_timeout_ms, DEFAULT_RULES.llm_image_timeout_ms, DEFAULT_RULES.llm_retries) == (
        5_000,
        8_000,
        1,
    )


async def test_gives_a_turn_with_images_the_longer_time_limit() -> None:
    rules = replace(DEFAULT_RULES, llm_timeout_ms=111, llm_image_timeout_ms=222)
    llm = ScriptedLlm()
    llm.push(turn_json(category_id=2), turn_json(category_id=2))
    await interpret_turn(llm, CTX, rules)
    image = ImageData(b"PNG", "image/png")
    await interpret_turn(llm, replace(CTX, images=(image,)), rules)
    assert [r.timeout_ms for r in llm.requests] == [111, 222]


async def test_times_each_attempt_and_says_how_it_ended() -> None:
    llm = ScriptedLlm()
    llm.push(TimeoutError(), RuntimeError("HTTP 500"), "not json", turn_json(category_id=99), turn_json(category_id=2))
    result = await interpret_turn(llm, CTX, replace(DEFAULT_RULES, llm_retries=4))
    assert result.outcomes == ("timeout", "error", "invalid", "invalid", "ok")
    assert len(result.attempts_ms) == 5
    assert all(isinstance(ms, int) and ms >= 0 for ms in result.attempts_ms)
