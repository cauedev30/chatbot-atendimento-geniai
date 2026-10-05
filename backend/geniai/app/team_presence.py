"""Whether the team is talking in a conversation (owner, 2026-10-05): a person of the team wrote in it after
a given time, so the bot stays out. Read from Chatwoot's API, since the webhook brings only the customer's
messages. A team message is one sent from Chatwoot (message_type 1), not a private note, not the WhatsApp
connector's echo, and not one of the bot's own messages, which Chatwoot shows alike and which only the ids
kept in the outbox tell apart (see outbox.sent_message_ids)."""

from datetime import datetime

from geniai.app.outbox import sent_message_ids
from geniai.app.ports import ChatwootMessage, Deps


def is_team_message(m: ChatwootMessage, bot_ids: set[int]) -> bool:
    return m.outgoing and not m.private and not m.echo and m.id not in bot_ids


async def team_wrote_since(deps: Deps, conversation_id: int, since: datetime | None) -> bool:
    """`since` None: at any time. When Chatwoot does not answer, logs a warning and returns False: the bot
    carries on as before."""
    try:
        messages = await deps.chatwoot.list_messages(conversation_id)
    except Exception as err:
        deps.log.warn({"err": err, "conversationId": conversation_id}, "team check failed; the bot carries on")
        return False
    async with deps.engine.connect() as conn:
        bot_ids = await sent_message_ids(conn, conversation_id)
        await conn.rollback()
    return any(is_team_message(m, bot_ids) and (since is None or m.at > since) for m in messages)
