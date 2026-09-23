"""What the routes read from the running app: configuration, use-case deps, scheduler and queue."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from geniai.api.login_limit import LoginLimiter
from geniai.app.keyed_queue import KeyedQueue
from geniai.app.ports import Deps
from geniai.app.turn_scheduler import TurnScheduler

if TYPE_CHECKING:
    from geniai.config import AppConfig

INVALID_REQUEST = "Pedido inválido."


@dataclass
class AppState:
    config: "AppConfig"
    queue: KeyedQueue
    deps: Deps | None = None
    """Set at startup by the lifespan, or injected by tests."""
    scheduler: TurnScheduler | None = None
    login_limiter: LoginLimiter = field(default_factory=LoginLimiter)


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.geniai
    return state


def app_config(request: Request) -> "AppConfig":
    return app_state(request).config


def app_deps(request: Request) -> Deps:
    deps = app_state(request).deps
    if deps is None:
        raise RuntimeError("the app is not started")
    return deps


def app_scheduler(request: Request) -> TurnScheduler:
    scheduler = app_state(request).scheduler
    if scheduler is None:
        raise RuntimeError("the app is not started")
    return scheduler


def require_json(request: Request) -> None:
    """Mutations accept application/json only; with the SameSite=Lax cookie, no cross-site form reaches them."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(400, INVALID_REQUEST)
