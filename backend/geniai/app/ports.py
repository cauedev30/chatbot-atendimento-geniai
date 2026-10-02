from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncEngine

from geniai.app.card_summaries import CardSummaries
from geniai.app.outbox import Outbox
from geniai.domain.rules import TriageRules


@dataclass(frozen=True)
class ImageData:
    """An image in memory, never written to disk or to the database."""

    data: bytes
    content_type: str
    """image/jpeg, image/png or image/webp."""


@dataclass(frozen=True)
class AudioData:
    """An audio in memory, never written to disk or to the database."""

    data: bytes
    content_type: str
    """One of geniai.audio.AUDIO_FORMATS."""
    seconds: float | None
    """How long it lasts, read from the file (Ogg Opus); None when the format's duration is not read."""


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    timeout_ms: int
    images: tuple[ImageData, ...] = ()
    """Sent with the user message, in the order of the "[imagem N]" labels of its text."""


class LlmPort(Protocol):
    """The model behind the bot. Adapters return the raw text; validation happens in llm/interpret.py."""

    async def complete(self, request: LlmRequest) -> str: ...


ChatwootStatus = Literal["open", "resolved", "pending"]


class ChatwootPort(Protocol):
    async def send_message(self, conversation_id: int, text: str) -> None: ...

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None: ...

    def conversation_url(self, conversation_id: int) -> str: ...


FetchFailureReason = Literal["host", "redirects", "status", "type", "size", "empty", "timeout", "error"]


@dataclass(frozen=True)
class FetchFailure:
    """Why an image or an audio was not downloaded, for the log: never the link nor the bytes."""

    reason: FetchFailureReason
    content_type: str | None = None
    size: int | None = None
    """Bytes, when known."""


class MediaFetcher(Protocol):
    """Downloads a customer's image from Chatwoot for the turn. Never raises: a failure is a result."""

    async def fetch_image(self, url: str) -> ImageData | FetchFailure: ...


class AudioFetcher(Protocol):
    """Downloads a customer's audio from Chatwoot for the turn. Never raises: a failure is a result."""

    async def fetch_audio(self, url: str) -> AudioData | FetchFailure: ...


class Logger(Protocol):
    def info(self, obj: dict[str, object], msg: str | None = None) -> None: ...

    def warn(self, obj: dict[str, object], msg: str | None = None) -> None: ...

    def error(self, obj: dict[str, object], msg: str | None = None) -> None: ...


@dataclass
class Deps:
    """Mutable on purpose: tests swap `rules` (see Harness.with_rules)."""

    engine: AsyncEngine
    llm: LlmPort
    chatwoot: ChatwootPort
    rules: TriageRules
    now: Callable[[], datetime]
    log: Logger
    outbox: Outbox = field(default_factory=Outbox)
    summaries: CardSummaries = field(default_factory=CardSummaries)
    """The card summaries written in the background, once the LLM is free (see app/card_summaries.py)."""
    bot_only_phones: frozenset[str] = frozenset()
    """Test mode (BOT_ONLY_PHONES): when not empty, the only phones the bot serves; see domain/audience.py."""
    media: MediaFetcher | None = None
    """Downloads customer images for the LLM; None when image reading is off (LLM_READS_IMAGES=false)."""
