import pytest

from geniai.domain.phone import normalize_br_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+55 (11) 90000-0001", "+5511900000001"),
        ("5511900000001", "+5511900000001"),
        ("11900000001", "+5511900000001"),
    ],
)
def test_keeps_a_13_digit_mobile(raw: str, expected: str) -> None:
    assert normalize_br_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("551190000001", "+5511990000001"),
        ("+55 11 9000-0001", "+5511990000001"),
        ("(11) 9000-0001", "+5511990000001"),
        ("1190000001", "+5511990000001"),
    ],
)
def test_adds_the_9th_digit_to_a_12_digit_mobile(raw: str, expected: str) -> None:
    assert normalize_br_phone(raw) == expected


def test_leaves_landlines_with_8_digits() -> None:
    assert normalize_br_phone("+55 11 3000-0001") == "+551130000001"


@pytest.mark.parametrize(
    "raw",
    ["+1 415 555 0100", "123456789012345", "", "+55 11 80000-0001", "+55 01 90000-0001", "abc"],
)
def test_rejects_what_is_not_a_brazilian_number(raw: str) -> None:
    assert normalize_br_phone(raw) is None
