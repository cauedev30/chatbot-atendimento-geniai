from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError, field_validator

from geniai.domain.types import ATTACHMENT_KINDS, Attachment, AttachmentKind
from geniai.json_types import JsonInt


@dataclass(frozen=True)
class IncomingMessage:
    kind: ClassVar[Literal["incoming_message"]] = "incoming_message"
    message_id: int
    conversation_id: int
    phone: str | None
    text: str
    """The message text, or the caption of its attachments; "" when there is none."""
    conversation_status: str | None
    """Chatwoot conversation status at delivery ("pending" while the bot handles it); None when absent."""
    contact_identifier: str | None = None
    """The contact's identifier in Chatwoot (a WhatsApp connector may put the chat id here, which ends in
    "@g.us" for a group); None when absent."""
    attachments: tuple[Attachment, ...] = ()

    @property
    def has_media(self) -> bool:
        return len(self.attachments) > 0


@dataclass(frozen=True)
class ConversationResolved:
    kind: ClassVar[Literal["conversation_resolved"]] = "conversation_resolved"
    conversation_id: int


@dataclass(frozen=True)
class Ignored:
    kind: ClassVar[Literal["ignored"]] = "ignored"
    reason: str


ChatwootEvent = IncomingMessage | ConversationResolved | Ignored


class _Phone(BaseModel):
    phone_number: StrictStr | None = None
    identifier: StrictStr | None = None


class _Meta(BaseModel):
    sender: _Phone | None = None


class _Conversation(BaseModel):
    id: JsonInt
    status: StrictStr | None = None
    meta: _Meta | None = None


class _Attachment(BaseModel):
    """Only what the bot reads of Chatwoot's attachment (id, message_id, file_type, account_id, extension,
    data_url, thumb_url, file_size). Loose on purpose: an odd attachment must not drop the message."""

    file_type: object = None
    data_url: object = None


def attachment_of(raw: _Attachment) -> Attachment:
    """The one place that maps a Chatwoot attachment: `file_type` image, audio or video is that kind,
    anything else (or nothing) is a file; the link is `data_url`. The real payload of the WhatsApp
    connector is still to be checked with a photo."""
    kind: AttachmentKind = "file"
    for known in ATTACHMENT_KINDS:
        if raw.file_type == known:
            kind = known
    url = raw.data_url if isinstance(raw.data_url, str) and raw.data_url != "" else None
    return Attachment(kind, url)


class _MessageCreated(BaseModel):
    event: Literal["message_created"]
    id: JsonInt
    content: StrictStr | None = None
    message_type: StrictStr | StrictInt | StrictFloat
    private: StrictBool | None = None
    conversation: _Conversation
    sender: _Phone | None = None
    attachments: list[_Attachment] | None = None


class _StatusChanged(BaseModel):
    event: Literal["conversation_status_changed", "conversation_resolved"]
    id: JsonInt
    status: StrictStr | None = None
    """May be absent; an explicit null is not a status, so the event is ignored."""

    @field_validator("status", mode="before")
    @classmethod
    def _present_status_is_text(cls, value: object) -> object:
        if value is None:
            raise ValueError("status is null")
        return value


class _Event(BaseModel):
    event: StrictStr


def parse_chatwoot_event(body: object) -> ChatwootEvent:
    """Validates a Chatwoot webhook body (Agent Bot or account webhook) and keeps only what the bot uses."""
    try:
        event = _Event.model_validate(body)
    except ValidationError:
        return Ignored("not a Chatwoot event")

    if event.event == "message_created":
        try:
            m = _MessageCreated.model_validate(body)
        except ValidationError:
            return Ignored("unexpected message_created shape")
        if m.message_type != "incoming" and m.message_type != 0:
            return Ignored("not incoming")
        if m.private is True:
            return Ignored("private note")
        text = (m.content or "").strip()
        attachments = tuple(attachment_of(a) for a in m.attachments or [])
        if text == "" and not attachments:
            return Ignored("empty message")
        meta_sender = m.conversation.meta.sender if m.conversation.meta else None
        phone = m.sender.phone_number if m.sender else None
        if phone is None and meta_sender:
            phone = meta_sender.phone_number
        identifier = m.sender.identifier if m.sender else None
        if identifier is None and meta_sender:
            identifier = meta_sender.identifier
        return IncomingMessage(
            message_id=m.id,
            conversation_id=m.conversation.id,
            phone=phone,
            text=text,
            conversation_status=m.conversation.status,
            contact_identifier=identifier,
            attachments=attachments,
        )

    try:
        status = _StatusChanged.model_validate(body)
    except ValidationError:
        return Ignored(f"event {event.event}")
    if status.event == "conversation_resolved" or status.status == "resolved":
        return ConversationResolved(conversation_id=status.id)
    return Ignored(f"status {status.status or 'unknown'}")
