import pytest

from geniai.domain.audience import not_served_reason

LIST = frozenset({"+5511900000001"})


def test_serves_every_phone_when_the_test_list_is_empty() -> None:
    assert not_served_reason("+5511900000002", None, frozenset()) is None


def test_serves_a_listed_phone_written_in_any_format() -> None:
    assert not_served_reason("11 90000-0001", "5511900000001@c.us", LIST) is None


def test_does_not_serve_a_phone_outside_the_test_list() -> None:
    assert not_served_reason("+5511900000002", None, LIST) == "not_in_test_list"


@pytest.mark.parametrize("only", [frozenset(), LIST])
@pytest.mark.parametrize(
    ("phone", "identifier"),
    [
        ("+5511900000001", "120363000000000001@g.us"),
        (None, "120363000000000001@G.US"),
        ("120363000000000001@g.us", None),
    ],
)
def test_never_serves_a_group(phone: str | None, identifier: str | None, only: frozenset[str]) -> None:
    assert not_served_reason(phone, identifier, only) == "group"


@pytest.mark.parametrize("only", [frozenset(), LIST])
@pytest.mark.parametrize("phone", [None, "", "+120363000000000001", "123456789012345"])
def test_never_serves_a_contact_without_a_usable_phone(phone: str | None, only: frozenset[str]) -> None:
    assert not_served_reason(phone, None, only) == "no_phone"
