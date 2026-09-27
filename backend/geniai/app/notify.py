from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.app.outbox import enqueue_message, enqueue_status
from geniai.domain.transitions import chatwoot_status_after_move
from geniai.domain.types import Column

__all__ = ["enqueue_message", "enqueue_status", "enqueue_status_after_move"]


async def enqueue_status_after_move(conn: AsyncConnection, conversation_id: int, from_: Column, to: Column) -> None:
    """Mirrors a ticket move on the Chatwoot conversation status, in the transaction of the move."""
    status = chatwoot_status_after_move(from_, to)
    if status is not None:
        await enqueue_status(conn, conversation_id, status)
