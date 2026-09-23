from dataclasses import dataclass
from datetime import datetime, timedelta

from geniai.domain.rules import TriageRules
from geniai.domain.types import Column


@dataclass(frozen=True)
class SilenceInput:
    column: Column
    faq_attempted: bool
    last_customer_message_at: datetime


def is_silent(t: SilenceInput, now: datetime, rules: TriageRules) -> bool:
    """Spec §5.1 step 9: a ticket in triage with no customer message for the timeout goes to "No response"."""
    if t.column != "in_triage":
        return False
    # OWNER-UNCONFIRMED: by default the rule also applies before the FAQ hint was sent.
    if not t.faq_attempted and not rules.silence_applies_before_faq:
        return False
    return now - t.last_customer_message_at >= timedelta(milliseconds=rules.silence_timeout_ms)
