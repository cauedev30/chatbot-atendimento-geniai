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
    max_faq_questions: int
    """Spec §5.1 step 5: questions about the FAQ entry sent that the bot answers; the next one hands over."""
    llm_timeout_ms: int
    """OWNER-UNCONFIRMED: time limit of one LLM call in a turn with text only (spec §10: one retry)."""
    llm_image_timeout_ms: int
    """OWNER-UNCONFIRMED: time limit of one LLM call in a turn with images, which the model reads slower."""
    llm_retries: int
    max_images_per_turn: int
    """OWNER-UNCONFIRMED: images the LLM reads in one turn, the most recent ones; older ones are only named."""
    max_image_bytes: int
    """OWNER-UNCONFIRMED: largest image the bot downloads; a bigger one is treated as one that did not open."""
    image_download_timeout_ms: int
    """OWNER-UNCONFIRMED: time limit of one image download from Chatwoot."""


DEFAULT_RULES = TriageRules(
    burst_window_ms=5_000,
    silence_timeout_ms=24 * 60 * 60 * 1000,
    silence_applies_before_faq=True,
    max_unclear_feedback_reasks=1,
    max_media_prompts=1,
    take_asks_who_takes=True,
    max_clarifications=2,
    max_faq_questions=3,
    llm_timeout_ms=5_000,
    llm_image_timeout_ms=8_000,
    llm_retries=1,
    max_images_per_turn=4,
    max_image_bytes=5 * 1024 * 1024,
    image_download_timeout_ms=15_000,
)
