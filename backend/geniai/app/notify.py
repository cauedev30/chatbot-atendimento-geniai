from geniai.app.outbox import safely
from geniai.app.ports import Deps
from geniai.domain.transitions import chatwoot_status_after_move
from geniai.domain.types import Column

__all__ = ["safely", "send_message", "sync_chatwoot_status"]


async def send_message(deps: Deps, conversation_id: int, text: str) -> None:
    await deps.outbox.run(
        deps.log, conversation_id, "send message", lambda: deps.chatwoot.send_message(conversation_id, text)
    )


async def sync_chatwoot_status(deps: Deps, conversation_id: int, from_: Column, to: Column) -> None:
    status = chatwoot_status_after_move(from_, to)
    if status is not None:
        await deps.outbox.run(
            deps.log,
            conversation_id,
            f"set conversation {status}",
            lambda: deps.chatwoot.set_status(conversation_id, status),
        )
