"""The messages of a conversation, as Chatwoot's API lists them (GET .../conversations/{id}/messages): only
what tells who wrote each one. Facts read on 2026-10-05: the bot's messages and the team's look alike
(message_type 1, sender "user"); the WhatsApp connector echoes each message sent (message_type 1, sender
"agent_bot", content_attributes.external_echo); notes are private; activities are message_type 2."""

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError

from geniai.app.ports import ChatwootMessage
from geniai.json_types import JsonInt


class _ApiMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: JsonInt
    message_type: StrictStr | StrictInt | StrictFloat
    created_at: StrictInt | StrictFloat
    """Seconds since the epoch."""
    private: StrictBool | None = None
    content_attributes: object = None


def _is_echo(attributes: object) -> bool:
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except ValueError:
            return False
    return isinstance(attributes, dict) and attributes.get("external_echo") is True


def parse_conversation_messages(body: object) -> list[ChatwootMessage]:
    """Raises ValueError when the answer has no list of messages; a message it cannot read is left out."""
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, list):
        raise ValueError("Chatwoot answer without a list of messages")
    messages: list[ChatwootMessage] = []
    for raw in payload:
        try:
            m = _ApiMessage.model_validate(raw)
        except ValidationError:
            continue
        messages.append(
            ChatwootMessage(
                id=m.id,
                at=datetime.fromtimestamp(m.created_at, UTC),
                outgoing=m.message_type in (1, "outgoing"),
                private=m.private is True,
                echo=_is_echo(m.content_attributes),
            )
        )
    return messages
