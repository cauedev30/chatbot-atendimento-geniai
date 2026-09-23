import pytest

from geniai.domain.phone import normalize_br_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+55 (11) 98765-4321", "+5511987654321"),
        ("5511987654321", "+5511987654321"),
        ("11987654321", "+5511987654321"),
    ],
)
def test_keeps_a_13_digit_mobile(raw: str, expected: str) -> None:
    assert normalize_br_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("551187654321", "+5511987654321"),
        ("+55 11 8765-4321", "+5511987654321"),
        ("(11) 8765-4321", "+5511987654321"),
        ("1187654321", "+5511987654321"),
    ],
)
def test_adds_the_9th_digit_to_a_12_digit_mobile(raw: str, expected: str) -> None:
    assert normalize_br_phone(raw) == expected


def test_leaves_landlines_with_8_digits() -> None:
    assert normalize_br_phone("+55 11 3333-4444") == "+551133334444"


@pytest.mark.parametrize(
    "raw",
    ["+1 415 555 0100", "123456789012345", "", "+55 11 88765-4321", "+55 01 98765-4321", "abc"],
)
def test_rejects_what_is_not_a_brazilian_number(raw: str) -> None:
    assert normalize_br_phone(raw) is None
