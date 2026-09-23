from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError

from geniai.json_types import JsonInt


@dataclass(frozen=True)
class IncomingMessage:
    kind: ClassVar[Literal["incoming_message"]] = "incoming_message"
    message_id: int
    conversation_id: int
    phone: str | None
    text: str
    has_media: bool
    conversation_status: str | None
    """Chatwoot conversation status at delivery ("pending" while the bot handles it); None when absent."""


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


class _Meta(BaseModel):
    sender: _Phone | None = None


class _Conversation(BaseModel):
    id: JsonInt
    status: StrictStr | None = None
    meta: _Meta | None = None


class _Attachment(BaseModel):
    file_type: StrictStr | None = None


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
        has_media = len(m.attachments or []) > 0
        if text == "" and not has_media:
            return Ignored("empty message")
        phone = m.sender.phone_number if m.sender else None
        if phone is None and m.conversation.meta and m.conversation.meta.sender:
            phone = m.conversation.meta.sender.phone_number
        return IncomingMessage(
            message_id=m.id,
            conversation_id=m.conversation.id,
            phone=phone,
            text=text,
            has_media=has_media,
            conversation_status=m.conversation.status,
        )

    try:
        status = _StatusChanged.model_validate(body)
    except ValidationError:
        return Ignored(f"event {event.event}")
    if status.event == "conversation_resolved" or status.status == "resolved":
        return ConversationResolved(conversation_id=status.id)
    return Ignored(f"status {status.status or 'unknown'}")
