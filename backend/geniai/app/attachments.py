"""The attachments of a turn: which images are downloaded for the LLM, how every attachment is named in
the text the LLM reads, and what the turn records about each image afterwards.

An image is read once. Until an LLM turn has read its message, its outcome is None; that turn downloads
it (the most recent max_images_per_turn of them), sends it and stores the LLM's description, and later
turns show the description instead of sending the image again. An image in a turn decided before the
LLM (the greeting, a request for a person, a request for text) stays unread for the next LLM turn.

An audio is transcribed before the turn decides anything (app/transcription.py): once transcribed, it
counts as text everywhere here; otherwise it is an attachment the bot cannot open.
"""

import asyncio
from dataclasses import dataclass, field, replace

from geniai.app.ports import Deps, FetchFailure, ImageData
from geniai.app.tickets_repo import MessageRow
from geniai.domain import attachments as label
from geniai.domain.types import Attachment, ImageOutcome, UnreadMedia

Slot = tuple[int, int]
"""An attachment: its message id and its position in the message."""

IMAGE_UNREAD = "[imagem]"
"""For the team only (a card summary made of the customer's words): an image no LLM turn has read."""


@dataclass(frozen=True)
class TurnImages:
    """What one turn does with the unread images: sent to the LLM (numbered from 1, in order), not opened,
    or past the limit."""

    sent: dict[Slot, int] = field(default_factory=dict)
    images: tuple[ImageData, ...] = ()
    failed: frozenset[Slot] = frozenset()
    over_limit: frozenset[Slot] = frozenset()

    def outcome(self, slot: Slot) -> ImageOutcome | None:
        if slot in self.sent:
            return "seen"
        if slot in self.over_limit:
            return "over_limit"
        return "failed" if slot in self.failed else None


NO_IMAGES = TurnImages()


def _is_legacy_media(m: MessageRow) -> bool:
    """A media-only message stored before attachments were kept: the bot never knew what it was."""
    return m.is_media and not m.attachments


def _transcript(a: Attachment) -> str | None:
    """What an audio said, once transcribed; None for anything else."""
    return a.transcript if a.kind == "audio" and a.outcome == "transcribed" and a.transcript else None


def customer_words(pending: list[MessageRow]) -> list[str]:
    """What the customer wrote or said in the turn's messages: what each transcribed audio said, then each
    text or caption, in order."""
    words: list[str] = []
    for m in pending:
        words += [said for a in m.attachments if (said := _transcript(a))]
        if not m.is_media:
            words.append(m.text)
    return words


def has_unheard_media(pending: list[MessageRow]) -> bool:
    """Whether the turn's messages carry something besides words: a photo, a video, a file, or an audio that
    was not transcribed."""
    return any(_is_legacy_media(m) or any(_transcript(a) is None for a in m.attachments) for m in pending)


def _unread_images(messages: list[MessageRow]) -> list[tuple[Slot, Attachment]]:
    return [
        ((m.id, i), a)
        for m in messages
        if m.author == "customer"
        for i, a in enumerate(m.attachments)
        if a.kind == "image" and a.outcome is None
    ]


def may_be_legible(pending: list[MessageRow]) -> bool:
    """Whether the turn can have anything the LLM reads, before any image download: words (text or a
    transcribed audio), or an unread image."""
    return bool(customer_words(pending)) or bool(_unread_images(pending))


def is_legible(pending: list[MessageRow], turn: TurnImages) -> bool:
    return bool(customer_words(pending)) or any(
        (m.id, i) in turn.sent for m in pending for i in range(len(m.attachments))
    )


def unread_media(pending: list[MessageRow], reads_images: bool) -> UnreadMedia:
    """For a turn with nothing legible: what to ask the customer to type instead of."""
    if not reads_images:
        return "media"
    others = any(_is_legacy_media(m) or any(a.kind != "image" for a in m.attachments) for m in pending)
    return "other" if others else "image"


async def read_images(deps: Deps, ticket_id: int, messages: list[MessageRow]) -> TurnImages:
    """Downloads the most recent unread images of the ticket's customer messages, at most
    max_images_per_turn; the older ones are past the limit. With image reading off nothing is downloaded
    and every unread image counts as not opened. Logs each image by type and size, never its link."""
    unread = _unread_images(messages)
    if deps.media is None:
        return TurnImages(failed=frozenset(slot for slot, _ in unread))
    limit = deps.rules.max_images_per_turn
    older, chosen = unread[: max(0, len(unread) - limit)], unread[max(0, len(unread) - limit) :]
    media = deps.media

    async def fetch(a: Attachment) -> ImageData | FetchFailure:
        return FetchFailure("host") if a.url is None else await media.fetch_image(a.url)

    results = await asyncio.gather(*(fetch(a) for _, a in chosen))
    sent: dict[Slot, int] = {}
    images: list[ImageData] = []
    failed: set[Slot] = set()
    for (slot, _), result in zip(chosen, results, strict=True):
        if isinstance(result, ImageData):
            images.append(result)
            sent[slot] = len(images)
            deps.log.info(
                {"ticketId": ticket_id, "contentType": result.content_type, "size": len(result.data)}, "image read"
            )
        else:
            failed.add(slot)
            deps.log.info(
                {
                    "ticketId": ticket_id,
                    "reason": result.reason,
                    "contentType": result.content_type,
                    "size": result.size,
                },
                "image not read",
            )
    return TurnImages(sent, tuple(images), frozenset(failed), frozenset(slot for slot, _ in older))


def _label(m: MessageRow, i: int, a: Attachment, turn: TurnImages | None) -> str:
    match a.kind:
        case "audio":
            said = _transcript(a)
            return label.AUDIO if said is None else label.audio_transcribed(said)
        case "video":
            return label.VIDEO
        case "file":
            return label.FILE
    slot = (m.id, i)
    if turn is not None and slot in turn.sent:
        return label.image_sent(turn.sent[slot])
    outcome = a.outcome if turn is None or turn.outcome(slot) is None else turn.outcome(slot)
    if outcome == "seen":
        return label.image_seen(a.description or label.IMAGE_SEEN_FALLBACK)
    if outcome == "over_limit":
        return label.IMAGE_OVER_LIMIT
    if outcome == "failed":
        return label.IMAGE_FAILED
    return IMAGE_UNREAD


def message_text(m: MessageRow, turn: TurnImages | None = None) -> str:
    """A message as the LLM (with the turn's images) or the team (turn None) reads it: the labels of its
    attachments (a transcribed audio by what it said), then its text or caption."""
    labels = [_label(m, i, a, turn) for i, a in enumerate(m.attachments)]
    if _is_legacy_media(m):
        labels.append(label.FILE)
    return " ".join([*labels, *([] if m.is_media else [m.text])]).strip()


def with_outcomes(messages: list[MessageRow], turn: TurnImages, descriptions: tuple[str, ...]) -> list[MessageRow]:
    """The messages whose images this turn read, with each image's outcome and, when seen, the LLM's
    description of it (or IMAGE_SEEN_FALLBACK when it gave none)."""
    changed: list[MessageRow] = []
    for m in messages:
        updated = list(m.attachments)
        for i, a in enumerate(m.attachments):
            outcome = turn.outcome((m.id, i))
            if outcome is None:
                continue
            description = None
            if outcome == "seen":
                n = turn.sent[(m.id, i)]
                given = descriptions[n - 1] if n <= len(descriptions) else ""
                description = given or label.IMAGE_SEEN_FALLBACK
            updated[i] = replace(a, outcome=outcome, description=description)
        if tuple(updated) != m.attachments:
            changed.append(replace(m, attachments=tuple(updated)))
    return changed
