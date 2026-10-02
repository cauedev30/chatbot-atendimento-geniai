from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TranscriberConfig:
    """An OpenAI-compatible audio transcription endpoint (TRANSCRIBE_*), set apart from the LLM's so either
    can change provider alone."""

    base_url: str
    api_key: str
    model: str
    transport: httpx.AsyncBaseTransport | None = None
    """Tests pass an httpx.MockTransport."""
