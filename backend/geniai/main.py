"""The service: JSON API under /api, the Chatwoot webhook, and the bot's background work.

Run it with `python -m geniai` (see __main__.py).
"""

import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response

from geniai.api import auth, board, indicators, webhook
from geniai.api.deps import INVALID_REQUEST, AppState
from geniai.api.schemas import HealthOut
from geniai.app.board import BoardError
from geniai.app.keyed_queue import KeyedQueue
from geniai.app.logging import ConsoleLogger
from geniai.app.outbox import OutboxWorker
from geniai.app.ports import Deps
from geniai.app.process_turn import run_turn
from geniai.app.silence_sweeper import resume_pending_turns, start_sweeper
from geniai.app.turn_scheduler import DebouncedScheduler, TurnScheduler
from geniai.chatwoot.http import create_chatwoot_http
from geniai.chatwoot.media import create_chatwoot_media
from geniai.config import AppConfig, load_config
from geniai.db.engine import create_engine
from geniai.db.migrate import migrate
from geniai.llm.openai_compatible import create_openai_compatible_llm

SWEEP_INTERVAL_S = 5 * 60

_WEBHOOK_TOKEN_IN_PATH = re.compile(r"^/webhooks/chatwoot/[^/]*")


def loggable_path(path: str) -> str:
    """The request path with the webhook token masked: it is a secret."""
    return _WEBHOOK_TOKEN_IN_PATH.sub("/webhooks/chatwoot/***", path)


def _lifespan(state: AppState) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Migrates, builds the real adapters, schedules turns under the queue, resumes pending turns and
    sweeps silent tickets every 5 minutes; stops everything on shutdown. Each HTTP adapter keeps its
    client, and so its open connections, until then: it is closed after the work that uses it stopped."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as clients:
            config = state.config
            log = ConsoleLogger()
            engine = create_engine(config.database_url)
            clients.push_async_callback(engine.dispose)
            applied = await migrate(engine)
            if applied:
                log.info({"applied": applied}, "migrations applied")
            llm = create_openai_compatible_llm(config.llm)
            clients.push_async_callback(llm.aclose)
            chatwoot = create_chatwoot_http(config.chatwoot)
            clients.push_async_callback(chatwoot.aclose)
            media = None
            if config.llm_reads_images:
                media = create_chatwoot_media(
                    config.chatwoot,
                    max_bytes=config.rules.max_image_bytes,
                    timeout_ms=config.rules.image_download_timeout_ms,
                )
                clients.push_async_callback(media.aclose)
            deps = Deps(
                engine=engine,
                llm=llm,
                chatwoot=chatwoot,
                rules=config.rules,
                now=lambda: datetime.now(UTC),
                log=log,
                bot_only_phones=config.bot_only_phones,
                media=media,
            )
            async with _running(state, deps):
                yield

    return lifespan


@asynccontextmanager
async def _running(state: AppState, deps: Deps) -> AsyncIterator[None]:
    """The bot's background work: turns under the queue, the card summaries (which wait until the
    scheduler says the LLM is free), the outbox and the silence sweeper."""
    log = deps.log

    async def turn(conversation_id: int) -> None:
        await run_turn(state.queue, deps, conversation_id, scheduler)

    def on_error(err: BaseException, conversation_id: int) -> None:
        log.error({"err": err, "conversationId": conversation_id}, "turn processing failed")

    scheduler = DebouncedScheduler(state.config.rules.burst_window_ms, turn, on_error)
    deps.summaries.llm_free = scheduler.wait_idle
    state.deps, state.scheduler = deps, scheduler
    resumed = await resume_pending_turns(deps, scheduler)
    if resumed:
        log.info({"resumed": resumed}, "pending turns rescheduled")
    # Starts by sending what a previous run left pending.
    outbox_worker = OutboxWorker(deps)
    outbox_worker.start()
    sweeper = start_sweeper(deps, SWEEP_INTERVAL_S)
    try:
        yield
    finally:
        sweeper.cancel()
        await scheduler.stop()
        # After the turns, which may start one; a summary still waiting or running is dropped.
        await deps.summaries.stop()
        await outbox_worker.stop()


def create_app(
    config: AppConfig | None = None,
    *,
    deps: Deps | None = None,
    scheduler: TurnScheduler | None = None,
    queue: KeyedQueue | None = None,
) -> FastAPI:
    """Tests inject deps, a RecordingScheduler and a KeyedQueue; without deps, the lifespan builds the real ones."""
    state = AppState(config=config or load_config(), queue=queue or KeyedQueue(), deps=deps, scheduler=scheduler)
    docs = state.config.enable_api_docs
    app = FastAPI(
        title="GeniAI support bot",
        version="0.2.0",
        lifespan=None if deps is not None else _lifespan(state),
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.geniai = state

    @app.middleware("http")
    async def access_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        if state.deps is not None:
            state.deps.log.info(
                {
                    "method": request.method,
                    "path": loggable_path(request.url.path),
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000),
                },
                "request",
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": INVALID_REQUEST}, status_code=400)
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(BoardError)
    async def board_refused(_: Request, exc: BoardError) -> Response:
        return JSONResponse({"detail": exc.message}, status_code=400)

    @app.get("/api/health", tags=["health"])
    async def health() -> HealthOut:
        return HealthOut(ok=True)

    app.include_router(auth.router)
    app.include_router(board.router)
    app.include_router(indicators.router)
    app.include_router(webhook.router)

    def openapi() -> dict[str, Any]:
        # A malformed request answers 400 "Pedido inválido." (handler above), never FastAPI's 422.
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            for operations in schema.get("paths", {}).values():
                for operation in operations.values():
                    operation.get("responses", {}).pop("422", None)
            for name in ("HTTPValidationError", "ValidationError"):
                schema.get("components", {}).get("schemas", {}).pop(name, None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
