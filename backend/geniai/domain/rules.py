"""Every tunable of the conversation in one place.
OWNER-UNCONFIRMED marks details filled in on 2026-09-23 that the owner has not confirmed yet;
changing one of them must only require changing its value here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageRules:
    burst_window_ms: int
    """OWNER-UNCONFIRMED: silence that closes a burst of messages into one turn (spec §5.1 step 1)."""
    silence_timeout_ms: int
    """Silence that moves a ticket in triage to "No response" (spec §5.1 step 9)."""
    silence_applies_before_faq: bool
    """OWNER-UNCONFIRMED: the silence rule also applies before the FAQ hint was sent."""
    max_unclear_feedback_reasks: int
    """OWNER-UNCONFIRMED: how many times an unclear answer to "did it help?" is asked again."""
    max_media_prompts: int
    """OWNER-UNCONFIRMED: how many "please type it" replies media gets before the handoff."""
    take_asks_who_takes: bool
    """OWNER-UNCONFIRMED: "take" on the board requires choosing who takes the ticket."""
    max_clarifications: int
    """Spec §5.1 step 6: at most two clarifying questions."""
    llm_timeout_ms: int
    """Spec §10: LLM timeout (~8 s) and one retry."""
    llm_retries: int


DEFAULT_RULES = TriageRules(
    burst_window_ms=5_000,
    silence_timeout_ms=24 * 60 * 60 * 1000,
    silence_applies_before_faq=True,
    max_unclear_feedback_reasks=1,
    max_media_prompts=1,
    take_asks_who_takes=True,
    max_clarifications=2,
    llm_timeout_ms=8_000,
    llm_retries=1,
)
