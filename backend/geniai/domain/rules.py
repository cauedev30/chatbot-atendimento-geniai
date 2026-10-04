"""Every tunable of the conversation in one place.
OWNER-UNCONFIRMED marks details filled in on 2026-09-23 that the owner has not confirmed yet;
changing one of them must only require changing its value here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageRules:
    burst_window_ms: int
    """Silence that closes a burst of messages into one turn (spec §5.1 step 1), only until the bot's first
    reply in the ticket (owner, 2026-10-02; see app/turn_scheduler.py). 4 s is the minimum (owner, 2026-09-30)."""
    max_reply_hold_ms: int
    """A customer message that arrives while a turn prepares its reply drops that reply, and the next turn
    answers them all; but not once the turn's oldest message waited longer than this: then the reply goes
    (owner, 2026-10-02; see app/process_turn._claim)."""
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
    """Spec §5.1 step 6: at most one clarifying question, and only while the customer has not yet said what the
    problem is (owner, 2026-10-04); a clear request no FAQ entry covers goes to the support team at once."""
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
    max_audio_seconds: int
    """Longest audio the bot transcribes (owner, 2026-10-02); a longer one is treated as one it cannot hear.
    "2 minutos" is fixed in texts.ask_for_text_audio_too_long, attachments.AUDIO_TOO_LONG and the LLM prompt
    (llm/prompt.py): change them with it."""
    max_audio_bytes: int
    """Largest audio the bot downloads, as for an image; a bigger one is treated as one it cannot hear."""
    max_untimed_audio_bytes: int
    """Stands for max_audio_seconds when the duration is not read from the file (any format but Ogg Opus):
    about 2 min of a 128 kbps MP3 or M4A (owner, 2026-10-02). A larger audio counts as too long."""
    audio_download_timeout_ms: int
    """Time limit of one audio download from Chatwoot, as for an image."""
    transcribe_timeout_ms: int
    """Time limit of one audio transcription."""
    summary_deadline_ms: int
    """OWNER-UNCONFIRMED: time limit of the card summary after a handoff before the LLM, counting its wait
    for the LLM to be free and its calls; past it, the card gets the customer's own words."""


DEFAULT_RULES = TriageRules(
    burst_window_ms=4_000,
    max_reply_hold_ms=30_000,
    silence_timeout_ms=24 * 60 * 60 * 1000,
    silence_applies_before_faq=True,
    max_unclear_feedback_reasks=1,
    max_media_prompts=1,
    take_asks_who_takes=True,
    max_clarifications=1,
    max_faq_questions=3,
    llm_timeout_ms=5_000,
    llm_image_timeout_ms=8_000,
    llm_retries=1,
    max_images_per_turn=4,
    max_image_bytes=5 * 1024 * 1024,
    image_download_timeout_ms=15_000,
    max_audio_seconds=120,
    max_audio_bytes=5 * 1024 * 1024,
    max_untimed_audio_bytes=2 * 1024 * 1024,
    audio_download_timeout_ms=15_000,
    transcribe_timeout_ms=15_000,
    summary_deadline_ms=30_000,
)
