from collections.abc import Awaitable, Callable

from geniai.app.ports import Deps, Logger
from geniai.domain.transitions import chatwoot_status_after_move
from geniai.domain.types import Column


async def safely(log: Logger, what: str, fn: Callable[[], Awaitable[None]]) -> None:
    """Outbound calls never undo or block the database state (spec §10): the ticket is already written.
    Adapters retry; here the final failure is only logged.
    """
    try:
        await fn()
    except Exception as err:
        log.error({"err": err, "what": what}, "Chatwoot call failed")


async def sync_chatwoot_status(deps: Deps, conversation_id: int, from_: Column, to: Column) -> None:
    status = chatwoot_status_after_move(from_, to)
    if status is not None:
        await safely(deps.log, f"set conversation {status}", lambda: deps.chatwoot.set_status(conversation_id, status))
