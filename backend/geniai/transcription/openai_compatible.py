import asyncio
from dataclasses import dataclass
from typing import Final

import httpx
from pydantic import BaseModel, StrictStr

from geniai.app.ports import AudioData, TranscribeFailure
from geniai.audio import AUDIO_FORMATS
from geniai.http_client import pooled_client

LANGUAGE: Final = "pt"
"""The customers speak Brazilian Portuguese; telling the model makes the transcription faster and better."""


@dataclass(frozen=True)
class TranscriberConfig:
    """An OpenAI-compatible audio transcription endpoint (TRANSCRIBE_*), set apart from the LLM's so either
    can change provider alone."""

    base_url: str
    api_key: str
    model: str
    transport: httpx.AsyncBaseTransport | None = None
    """Tests pass an httpx.MockTransport."""


class _Transcription(BaseModel):
    text: StrictStr


class OpenAiCompatibleTranscriber:
    """POST {base_url}/audio/transcriptions, multipart: the audio as `file` (named with the extension the API
    recognizes its format by), `model` and `language`. The whole call has one time limit. Never raises.

    Keeps one HTTP client, and so its connections, until aclose() (see main.py)."""

    def __init__(self, cfg: TranscriberConfig, timeout_ms: int) -> None:
        self._cfg = cfg
        self._url = f"{cfg.base_url.rstrip('/')}/audio/transcriptions"
        self._timeout_s = timeout_ms / 1000
        self._client = pooled_client(cfg.transport, timeout=self._timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: AudioData) -> str | TranscribeFailure:
        name = f"audio.{AUDIO_FORMATS.get(audio.content_type, 'ogg')}"
        try:
            async with asyncio.timeout(self._timeout_s):
                res = await self._client.post(
                    self._url,
                    files={"file": (name, audio.data, audio.content_type)},
                    data={"model": self._cfg.model, "language": LANGUAGE},
                    headers={"authorization": f"Bearer {self._cfg.api_key}"},
                )
        except (TimeoutError, httpx.TimeoutException):
            return TranscribeFailure("timeout")
        except Exception:
            return TranscribeFailure("error")
        if not res.is_success:
            return TranscribeFailure("status", res.status_code)
        try:
            text = _Transcription.model_validate(res.json()).text.strip()
        except Exception:
            return TranscribeFailure("error")
        return text or TranscribeFailure("empty")


def create_openai_compatible_transcriber(cfg: TranscriberConfig, *, timeout_ms: int) -> OpenAiCompatibleTranscriber:
    return OpenAiCompatibleTranscriber(cfg, timeout_ms)
