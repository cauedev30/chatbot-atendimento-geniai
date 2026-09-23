from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncEngine

from geniai.app.outbox import Outbox
from geniai.domain.rules import TriageRules


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    timeout_ms: int


class LlmPort(Protocol):
    """The model behind the bot. Adapters return the raw text; validation happens in llm/interpret.py."""

    async def complete(self, request: LlmRequest) -> str: ...


ChatwootStatus = Literal["open", "resolved", "pending"]


class ChatwootPort(Protocol):
    async def send_message(self, conversation_id: int, text: str) -> None: ...

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None: ...

    def conversation_url(self, conversation_id: int) -> str: ...


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
