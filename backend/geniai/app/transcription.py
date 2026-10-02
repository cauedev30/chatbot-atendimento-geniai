"""The customer's audios: downloaded and transcribed at the start of the turn, before any decision, so what
the customer said counts as text for every rule (the greeting, a request for a person, the LLM).

An audio is transcribed once. Its outcome (transcribed with its text, too long, or not transcribed) is kept
on the attachment right away, and later turns use it. Each transcription also goes to the team as a
private note in the Chatwoot conversation, posted while the turn decides (see TranscriptNotes). What the
customer said never goes to the log.
"""

import asyncio
import time
from dataclasses import dataclass, replace

from geniai.app.ports import AudioData, AudioTranscription, Deps, FetchFailure, TranscribeFailure
from geniai.app.tickets_repo import MessageRow, TicketRow, set_message_attachments
from geniai.domain.attachments import MAX_TRANSCRIPT_LEN, transcript_note
from geniai.domain.rules import TriageRules
from geniai.domain.texts import truncate
from geniai.domain.types import Attachment

Slot = tuple[int, int]
"""An attachment: its message id and its position in the message."""


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def too_long(audio: AudioData, rules: TriageRules) -> bool:
    """Longer than max_audio_seconds; by its size when the duration was not read from the file."""
    if audio.seconds is not None:
        return audio.seconds > rules.max_audio_seconds
    return len(audio.data) > rules.max_untimed_audio_bytes


def _untranscribed(messages: list[MessageRow]) -> list[tuple[Slot, Attachment]]:
    return [
        ((m.id, i), a)
        for m in messages
        if m.author == "customer"
        for i, a in enumerate(m.attachments)
        if a.kind == "audio" and a.outcome is None
    ]


async def _hear(deps: Deps, transcription: AudioTranscription, ticket_id: int, a: Attachment) -> Attachment:
    """Downloads and transcribes one audio, and returns it with its outcome. Logs each step by type, size,
    duration and time, never the link nor the text."""
    got = FetchFailure("host") if a.url is None else await transcription.media.fetch_audio(a.url)
    if isinstance(got, FetchFailure):
        line: dict[str, object] = {"ticketId": ticket_id, "reason": got.reason}
        deps.log.info({**line, "contentType": got.content_type, "size": got.size}, "audio not read")
        return replace(a, outcome="failed")
    seconds = None if got.seconds is None else round(got.seconds, 1)
    deps.log.info(
        {"ticketId": ticket_id, "contentType": got.content_type, "size": len(got.data), "seconds": seconds},
        "audio read",
    )
    if too_long(got, deps.rules):
        deps.log.info({"ticketId": ticket_id, "reason": "too_long", "seconds": seconds}, "audio not transcribed")
        return replace(a, outcome="too_long")
    started = time.perf_counter()
    result = await transcription.transcriber.transcribe(got)
    ms = _ms_since(started)
    # One line: the label and the note show it in quotes.
    text = "" if isinstance(result, TranscribeFailure) else " ".join(result.split())
    if text == "":
        failure = result if isinstance(result, TranscribeFailure) else TranscribeFailure("empty")
        line = {"ticketId": ticket_id, "reason": failure.reason, "status": failure.status}
        deps.log.info({**line, "seconds": seconds, "ms": ms}, "audio not transcribed")
        return replace(a, outcome="failed")
    deps.log.info({"ticketId": ticket_id, "seconds": seconds, "ms": ms}, "audio transcribed")
    return replace(a, outcome="transcribed", transcript=truncate(text, MAX_TRANSCRIPT_LEN))


async def _post_note(deps: Deps, t: TicketRow, transcript: str) -> None:
    """A note that fails is logged and left: the turn goes on."""
    try:
        await deps.chatwoot.send_private_note(t.chatwoot_conversation_id, transcript_note(transcript))
    except Exception as err:
        deps.log.error({"err": err, "ticketId": t.id}, "transcript note failed")


async def _post_notes(deps: Deps, t: TicketRow, transcripts: list[str]) -> None:
    for transcript in transcripts:
        await _post_note(deps, t, transcript)


@dataclass(frozen=True)
class TranscriptNotes:
    """The private notes of the transcriptions a turn just made, posted in order in the background while the
    turn decides. Before anything reaches the customer, the turn waits for them (wait): in Chatwoot a note
    comes before the reply, and the turn does not add their time to its own."""

    task: asyncio.Task[None] | None = None

    async def wait(self) -> None:
        """Returns once every note was posted or failed (and logged); at once when there is none."""
        if self.task is not None:
            await self.task


NO_NOTES = TranscriptNotes()


async def transcribe_audios(
    deps: Deps, t: TicketRow, messages: list[MessageRow]
) -> tuple[list[MessageRow], TranscriptNotes]:
    """Transcribes, together, the customer audios of the ticket no turn tried yet, and keeps each outcome on
    its attachment. Returns the messages with their audios' outcomes, and the private notes of the
    transcriptions, already on their way. With transcription off, nothing happens and the audios stay as
    they are."""
    transcription = deps.transcription
    pending = _untranscribed(messages)
    if transcription is None or not pending:
        return messages, NO_NOTES
    results = await asyncio.gather(*(_hear(deps, transcription, t.id, a) for _, a in pending))
    outcomes = dict(zip((slot for slot, _ in pending), results, strict=True))
    touched = {message_id for message_id, _ in outcomes}
    updated = [
        replace(m, attachments=tuple(outcomes.get((m.id, i), a) for i, a in enumerate(m.attachments)))
        if m.id in touched
        else m
        for m in messages
    ]
    async with deps.engine.begin() as conn:
        for m in updated:
            if m.id in touched:
                await set_message_attachments(conn, m.id, m.attachments)
    transcripts = [a.transcript for a in results if a.transcript is not None]
    if not transcripts:
        return updated, NO_NOTES
    return updated, TranscriptNotes(asyncio.create_task(_post_notes(deps, t, transcripts)))
