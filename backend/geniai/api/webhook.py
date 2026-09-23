"""POST /webhooks/chatwoot/{token}: Chatwoot calls the backend directly (not under /api, not proxied)."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from geniai.api.auth import safe_equal
from geniai.api.deps import app_config, app_deps, app_scheduler, app_state
from geniai.app.board import on_conversation_resolved
from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.keyed_queue import conversation_key
from geniai.chatwoot.webhook import ConversationResolved, IncomingMessage, parse_chatwoot_event

router = APIRouter(tags=["webhook"])


@router.post("/webhooks/chatwoot/{token}", include_in_schema=False)
async def chatwoot_webhook(token: str, request: Request) -> Response:
    if not safe_equal(token, app_config(request).webhook_token):
        return Response(status_code=404)
    try:
        body: object = await request.json()
    except ValueError:
        body = None
    event = parse_chatwoot_event(body)
    # Webhooks of one conversation run in arrival order, never behind its turn (see KeyedQueue); the
    # Chatwoot calls they cause run afterwards, in the background (see Outbox).
    deps = app_deps(request)
    queue = app_state(request).queue
    if isinstance(event, IncomingMessage):
        scheduler = app_scheduler(request)
        outcome = await queue.run(
            conversation_key(event.conversation_id), lambda: handle_inbound_message(deps, scheduler, event)
        )
        return JSONResponse({"outcome": outcome})
    if isinstance(event, ConversationResolved):
        moved = await queue.run(
            conversation_key(event.conversation_id), lambda: on_conversation_resolved(deps, event.conversation_id)
        )
        return JSONResponse({"moved": moved})
    return JSONResponse({"ignored": event.reason})
