"""Shared login for the support team: one user and password, a signed session cookie."""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Annotated, Final

import itsdangerous
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from geniai.api.deps import app_config, require_json
from geniai.api.schemas import ErrorOut, LoginIn, MeOut

SESSION_COOKIE: Final = "geniai_board"
TWELVE_HOURS_S: Final = 12 * 60 * 60


@dataclass(frozen=True)
class AuthConfig:
    user: str
    password: str
    cookie_secret: str
    """Signs the session cookie; at least 32 characters."""
    secure_cookie: bool
    """True behind HTTPS (production); false only for local http."""


def safe_equal(a: str, b: str) -> bool:
    """Constant-time comparison that does not leak the length."""
    return hmac.compare_digest(hashlib.sha256(a.encode()).digest(), hashlib.sha256(b.encode()).digest())


def _signer(cfg: AuthConfig) -> itsdangerous.TimestampSigner:
    return itsdangerous.TimestampSigner(cfg.cookie_secret)


def session_value(cfg: AuthConfig) -> bytes:
    """What the cookie signs: a digest of the current password, so changing BOARD_PASSWORD ends every
    open session. Letters and digits only, so URL-encoding the cookie never alters it."""
    return b"v1" + hashlib.sha256(f"geniai-session:{cfg.password}".encode()).hexdigest()[:32].encode()


def issue_session(response: Response, cfg: AuthConfig) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _signer(cfg).sign(session_value(cfg)).decode(),
        max_age=TWELVE_HOURS_S,
        path="/",
        secure=cfg.secure_cookie,
        httponly=True,
        samesite="lax",
    )


def has_session(request: Request, cfg: AuthConfig) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return False
    try:
        return hmac.compare_digest(_signer(cfg).unsign(cookie, max_age=TWELVE_HOURS_S), session_value(cfg))
    except itsdangerous.BadSignature:
        return False


def require_login(request: Request) -> None:
    if not has_session(request, app_config(request).auth):
        raise HTTPException(401, "Faça login para continuar.")


UNAUTHORIZED: Final[dict[int | str, dict[str, object]]] = {401: {"model": ErrorOut}}

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/login",
    status_code=204,
    responses={401: {"model": ErrorOut}},
    dependencies=[Depends(require_json)],
)
async def login(body: LoginIn, request: Request, response: Response) -> None:
    cfg = app_config(request).auth
    user_ok = safe_equal(body.user, cfg.user)
    password_ok = safe_equal(body.password, cfg.password)
    if not (user_ok and password_ok):
        raise HTTPException(401, "Usuário ou senha incorretos.")
    issue_session(response, cfg)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    """Always clears the cookie, with or without a valid session."""
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


@router.get("/me", responses=UNAUTHORIZED)
async def me(request: Request, _: Annotated[None, Depends(require_login)]) -> MeOut:
    return MeOut(user=app_config(request).auth.user)
