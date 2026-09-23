"""The service: JSON API under /api, the Chatwoot webhook, and the bot's background work.

uvicorn geniai.main:create_app --factory --host 0.0.0.0 --port 8000
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
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
from geniai.app.ports import Deps
from geniai.app.process_turn import run_turn
from geniai.app.silence_sweeper import resume_pending_turns, start_sweeper
from geniai.app.turn_scheduler import DebouncedScheduler, TurnScheduler
from geniai.chatwoot.http import create_chatwoot_http
from geniai.config import AppConfig, load_config
from geniai.db.engine import create_engine
from geniai.db.migrate import migrate
from geniai.llm.openai_compatible import create_openai_compatible_llm

SWEEP_INTERVAL_S = 5 * 60


def _lifespan(state: AppState) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Migrates, builds the real adapters, schedules turns under the queue, resumes pending turns and
    sweeps silent tickets every 5 minutes; stops everything on shutdown."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        config = state.config
        log = ConsoleLogger()
        engine = create_engine(config.database_url)
        applied = await migrate(engine)
        if applied:
            log.info({"applied": applied}, "migrations applied")
        deps = Deps(
            engine=engine,
            llm=create_openai_compatible_llm(config.llm),
            chatwoot=create_chatwoot_http(config.chatwoot),
            rules=config.rules,
            now=lambda: datetime.now(UTC),
            log=log,
        )

        async def turn(conversation_id: int) -> None:
            await run_turn(state.queue, deps, conversation_id)

        def on_error(err: BaseException, conversation_id: int) -> None:
            log.error({"err": err, "conversationId": conversation_id}, "turn processing failed")

        scheduler = DebouncedScheduler(config.rules.burst_window_ms, turn, on_error)
        state.deps, state.scheduler = deps, scheduler
        resumed = await resume_pending_turns(deps, scheduler)
        if resumed:
            log.info({"resumed": resumed}, "pending turns rescheduled")
        sweeper = start_sweeper(deps, SWEEP_INTERVAL_S)
        try:
            yield
        finally:
            sweeper.cancel()
            await scheduler.stop()
            await deps.outbox.drain()
            await engine.dispose()

    return lifespan


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
