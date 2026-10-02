"""How the attachments of customer messages appear in the text the LLM reads.

Each attachment becomes a label next to the message's caption. The LLM prompt explains every label
(llm/prompt.py), so the model never takes an attachment it did not see for one that did not arrive.
"""

from typing import Final

IMAGE_FAILED: Final = "[imagem — não foi possível abrir]"
IMAGE_OVER_LIMIT: Final = "[imagem — além do limite, não vista]"
AUDIO: Final = "[áudio — o bot não ouve]"
"""An audio with transcription off."""
AUDIO_FAILED: Final = "[áudio — não foi possível ouvir]"
"""With transcription on, an audio not downloaded or not transcribed."""
AUDIO_TOO_LONG: Final = "[áudio — passou de 2 minutos, não ouvido]"
"""With transcription on, an audio longer than max_audio_seconds (2 min, fixed in the text)."""
VIDEO: Final = "[vídeo — o bot não abre]"
FILE: Final = "[arquivo — o bot não abre]"
IMAGE_SEEN_FALLBACK: Final = "[imagem vista pelo bot]"
"""Stored as the description of an image the LLM saw but did not describe."""
MAX_DESCRIPTION_LEN: Final = 300
MAX_TRANSCRIPT_LEN: Final = 3000
"""Longest transcription of an audio the bot keeps; a longer one is cut."""


def image_sent(n: int) -> str:
    """An image sent with this LLM call, numbered from 1 in the order of the request's images."""
    return f"[imagem {n}]"


def image_seen(description: str) -> str:
    """An image the LLM saw in an earlier turn, shown by its description instead of being sent again."""
    return description if description == IMAGE_SEEN_FALLBACK else f"[imagem: {description}]"


def audio_transcribed(transcript: str) -> str:
    """An audio the bot transcribed: what the customer said, for the LLM and the team."""
    return f'[áudio transcrito: "{transcript}"]'


def transcript_note(transcript: str) -> str:
    """The private note the team reads in the Chatwoot conversation after each transcription."""
    return f"Transcrição do áudio (bot): {transcript}"
