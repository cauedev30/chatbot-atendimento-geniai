import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from geniai.app.ports import AudioData, ChatwootStatus, FetchFailure, ImageData, LlmRequest, TranscribeFailure


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
        self.notes: list[Sent] = []
        self.fail_sends = False
        self.fail_notes = False
        self.hold_notes: asyncio.Event | None = None
        """When set, each private note waits for this event before it is posted."""

    async def send_message(self, conversation_id: int, text: str) -> None:
        if self.fail_sends:
            raise RuntimeError("chatwoot unavailable")
        self.sent.append(Sent(conversation_id, text))

    async def send_private_note(self, conversation_id: int, text: str) -> None:
        if self.hold_notes is not None:
            await self.hold_notes.wait()
        if self.fail_sends or self.fail_notes:
            raise RuntimeError("chatwoot unavailable")
        self.notes.append(Sent(conversation_id, text))

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None:
        if self.fail_sends:
            raise RuntimeError("chatwoot unavailable")
        self.statuses.append(StatusSet(conversation_id, status))

    def conversation_url(self, conversation_id: int) -> str:
        return f"https://chatwoot.example/app/accounts/1/conversations/{conversation_id}"


class FakeMedia:
    """Serves the images put in `images` and the audios put in `audios` by link; any other link fails as
    Chatwoot would with a 404."""

    def __init__(self) -> None:
        self.images: dict[str, ImageData | FetchFailure] = {}
        self.audios: dict[str, AudioData | FetchFailure] = {}
        self.fetched: list[str] = []

    async def fetch_image(self, url: str) -> ImageData | FetchFailure:
        self.fetched.append(url)
        return self.images.get(url, FetchFailure("status"))

    async def fetch_audio(self, url: str) -> AudioData | FetchFailure:
        self.fetched.append(url)
        return self.audios.get(url, FetchFailure("status"))


class FakeTranscriber:
    """Transcribes the audios put in `texts`, by their bytes; any other fails as the provider would with a 500."""

    def __init__(self) -> None:
        self.texts: dict[bytes, str | TranscribeFailure] = {}
        self.heard: list[AudioData] = []

    async def transcribe(self, audio: AudioData) -> str | TranscribeFailure:
        self.heard.append(audio)
        return self.texts.get(audio.data, TranscribeFailure("status", 500))


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
            "faq_answer_found": False,
            "handoff_reply": "",
            **fields,
        },
        ensure_ascii=False,
    )


def texts(sent: Iterable[Sent]) -> list[str]:
    return [s.text for s in sent]
