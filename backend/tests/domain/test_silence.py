from dataclasses import replace
from datetime import UTC, datetime, timedelta

from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.silence import SilenceInput, is_silent

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def hours_ago(h: int) -> datetime:
    return NOW - timedelta(hours=h)


def test_closes_a_ticket_in_triage_after_24_h_without_customer_messages() -> None:
    t = SilenceInput(column="in_triage", faq_attempted=True, last_customer_message_at=hours_ago(24))
    assert is_silent(t, NOW, DEFAULT_RULES) is True


def test_keeps_it_before_24_h() -> None:
    t = SilenceInput(column="in_triage", faq_attempted=True, last_customer_message_at=hours_ago(23))
    assert is_silent(t, NOW, DEFAULT_RULES) is False


def test_applies_before_the_faq_hint_by_default_owner_unconfirmed() -> None:
    t = SilenceInput(column="in_triage", faq_attempted=False, last_customer_message_at=hours_ago(25))
    assert is_silent(t, NOW, DEFAULT_RULES) is True


def test_can_be_limited_to_tickets_awaiting_faq_feedback() -> None:
    rules = replace(DEFAULT_RULES, silence_applies_before_faq=False)
    before = SilenceInput(column="in_triage", faq_attempted=False, last_customer_message_at=hours_ago(25))
    after = SilenceInput(column="in_triage", faq_attempted=True, last_customer_message_at=hours_ago(25))
    assert is_silent(before, NOW, rules) is False
    assert is_silent(after, NOW, rules) is True


def test_never_applies_outside_triage() -> None:
    t = SilenceInput(column="awaiting_human", faq_attempted=True, last_customer_message_at=hours_ago(99))
    assert is_silent(t, NOW, DEFAULT_RULES) is False
