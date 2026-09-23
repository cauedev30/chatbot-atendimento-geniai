from typing import Any

import pytest

from geniai.domain.types import InterpretedTurn
from geniai.llm.output_schema import parse_turn_output

CATEGORY_IDS = [1, 2, 7]
FAQ_ITEM_IDS = [10, 11]
VALID: dict[str, Any] = {
    "human_requested": False,
    "registration_mismatch": False,
    "off_topic": False,
    "category_id": 2,
    "faq_item_id": 10,
    "faq_feedback": None,
    "needs_clarification": False,
    "summary": "Não consegue entrar no painel.",
    "reply": "Veja se isto resolve:",
}


def parse(raw: object) -> InterpretedTurn:
    return parse_turn_output(raw, CATEGORY_IDS, FAQ_ITEM_IDS)


def test_maps_a_valid_output_to_code_naming() -> None:
    assert parse(VALID) == InterpretedTurn(
        human_requested=False,
        registration_mismatch=False,
        off_topic=False,
        category_id=2,
        faq_item_id=10,
        faq_feedback=None,
        needs_clarification=False,
        summary="Não consegue entrar no painel.",
        reply="Veja se isto resolve:",
    )


def test_rejects_a_category_outside_the_active_list() -> None:
    with pytest.raises(ValueError):
        parse(VALID | {"category_id": 99})


def test_treats_an_unknown_faq_id_as_none() -> None:
    assert parse(VALID | {"faq_item_id": 999}).faq_item_id is None


def test_drops_any_extra_field_so_there_is_no_way_to_request_an_action() -> None:
    parsed = parse(VALID | {"action": "remove_user"})
    assert not hasattr(parsed, "action")


def test_rejects_an_invalid_feedback_value_and_missing_fields() -> None:
    with pytest.raises(ValueError):
        parse(VALID | {"faq_feedback": "maybe"})
    without_summary = {k: v for k, v in VALID.items() if k != "summary"}
    with pytest.raises(ValueError):
        parse(without_summary)


@pytest.mark.parametrize(
    "override",
    [
        {"human_requested": "true"},
        {"off_topic": 1},
        {"category_id": "2"},
        {"category_id": True},
        {"category_id": 2.5},
        {"faq_item_id": "10"},
        {"summary": ""},
        {"summary": "x" * 1001},
        {"reply": "x" * 1001},
        {"reply": None},
    ],
)
def test_rejects_loose_types(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        parse(VALID | override)


def test_accepts_an_integral_json_number_and_an_empty_reply() -> None:
    parsed = parse(VALID | {"category_id": 2.0, "reply": ""})
    assert parsed.category_id == 2
    assert isinstance(parsed.category_id, int)


def test_rejects_a_non_object() -> None:
    with pytest.raises(ValueError):
        parse(["not", "an", "object"])
