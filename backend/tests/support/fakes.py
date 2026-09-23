import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from geniai.app.ports import ChatwootStatus, LlmRequest


@dataclass(frozen=True)
class Sent:
    conversation_id: int
    text: str


@dataclass(frozen=True)
class StatusSet:
    conversation_id: int
    status: ChatwootStatus


class FakeChatwoot:
    def __init__(self) -> None:
        self.sent: list[Sent] = []
        self.statuses: list[StatusSet] = []
        self.fail_sends = False

    async def send_message(self, conversation_id: int, text: str) -> None:
        if self.fail_sends:
            raise RuntimeError("chatwoot unavailable")
        self.sent.append(Sent(conversation_id, text))

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None:
        if self.fail_sends:
            raise RuntimeError("chatwoot unavailable")
        self.statuses.append(StatusSet(conversation_id, status))

    def conversation_url(self, conversation_id: int) -> str:
        return f"https://chatwoot.example/app/accounts/1/conversations/{conversation_id}"


class ScriptedLlm:
    """Returns scripted raw outputs in order; an Exception entry is raised instead."""

    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []
        self._queue: list[str | Exception] = []

    def push(self, *items: str | Exception) -> None:
        self._queue.extend(items)

    async def complete(self, request: LlmRequest) -> str:
        self.requests.append(request)
        if not self._queue:
            raise RuntimeError("ScriptedLlm: no scripted response left")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@dataclass(frozen=True)
class LogEntry:
    obj: dict[str, object]
    msg: str | None


class RecordingLogger:
    def __init__(self) -> None:
        self.infos: list[LogEntry] = []
        self.errors: list[LogEntry] = []
        self.warnings: list[LogEntry] = []

    def info(self, obj: dict[str, object], msg: str | None = None) -> None:
        self.infos.append(LogEntry(obj, msg))

    def warn(self, obj: dict[str, object], msg: str | None = None) -> None:
        self.warnings.append(LogEntry(obj, msg))

    def error(self, obj: dict[str, object], msg: str | None = None) -> None:
        self.errors.append(LogEntry(obj, msg))


class _SilentLogger:
    def info(self, obj: dict[str, object], msg: str | None = None) -> None:
        pass

    def warn(self, obj: dict[str, object], msg: str | None = None) -> None:
        pass

    def error(self, obj: dict[str, object], msg: str | None = None) -> None:
        pass


silent_logger = _SilentLogger()


def turn_json(**fields: Any) -> str:
    """A valid raw LLM output (spec §6) with defaults for every field but the category."""
    if "category_id" not in fields:
        raise TypeError("turn_json() needs category_id")
    return json.dumps(
        {
            "human_requested": False,
            "registration_mismatch": False,
            "off_topic": False,
            "faq_item_id": None,
            "faq_feedback": None,
            "needs_clarification": False,
            "summary": "Resumo de teste",
            "reply": "",
            **fields,
        },
        ensure_ascii=False,
    )


def texts(sent: Iterable[Sent]) -> list[str]:
    return [s.text for s in sent]
