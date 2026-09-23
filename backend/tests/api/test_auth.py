import time
from dataclasses import replace

import httpx
import itsdangerous

from geniai.api.auth import SESSION_COOKIE, safe_equal
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.main import create_app
from tests.api.conftest import TEST_CONFIG, Api
from tests.conftest import Harness


async def test_answers_401_without_a_session(api: Api) -> None:
    res = await api.client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json() == {"detail": "Faça login para continuar."}
    assert (await api.client.get("/api/board")).status_code == 401


async def test_health_needs_no_session(api: Api) -> None:
    res = await api.client.get("/api/health")
    assert (res.status_code, res.json()) == (200, {"ok": True})


async def test_rejects_a_wrong_password(api: Api) -> None:
    res = await api.client.post("/api/auth/login", json={"user": "suporte", "password": "errada"})
    assert res.status_code == 401
    assert res.json() == {"detail": "Usuário ou senha incorretos."}
    assert SESSION_COOKIE not in res.cookies


async def test_logs_in_with_a_signed_http_only_lax_cookie(api: Api) -> None:
    res = await api.client.post("/api/auth/login", json={"user": "suporte", "password": "senha-de-teste"})
    assert res.status_code == 204
    set_cookie = res.headers["set-cookie"]
    assert set_cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie or "SameSite=Lax" in set_cookie
    assert "Max-Age=43200" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" not in set_cookie


async def test_lets_a_logged_in_user_through(logged_in: Api) -> None:
    res = await logged_in.client.get("/api/auth/me")
    assert (res.status_code, res.json()) == (200, {"user": "suporte"})


async def test_rejects_an_unsigned_or_forged_cookie(api: Api) -> None:
    api.client.cookies.set(SESSION_COOKIE, "ok")
    assert (await api.client.get("/api/auth/me")).status_code == 401
    forged = itsdangerous.TimestampSigner("outro-segredo-com-mais-de-32-caracteres").sign(b"ok").decode()
    api.client.cookies.set(SESSION_COOKIE, forged)
    assert (await api.client.get("/api/auth/me")).status_code == 401


class _SignedHoursAgo(itsdangerous.TimestampSigner):
    def __init__(self, secret: str, hours: int) -> None:
        super().__init__(secret)
        self.hours = hours

    def get_timestamp(self) -> int:
        return int(time.time()) - self.hours * 3600


async def test_accepts_a_session_up_to_12_h_old_and_rejects_an_older_one(api: Api) -> None:
    secret = TEST_CONFIG.auth.cookie_secret
    api.client.cookies.set(SESSION_COOKIE, _SignedHoursAgo(secret, 11).sign(b"ok").decode())
    assert (await api.client.get("/api/auth/me")).status_code == 200
    api.client.cookies.set(SESSION_COOKIE, _SignedHoursAgo(secret, 13).sign(b"ok").decode())
    assert (await api.client.get("/api/auth/me")).status_code == 401


async def test_logs_out(logged_in: Api) -> None:
    res = await logged_in.client.post("/api/auth/logout")
    assert res.status_code == 204
    assert f'{SESSION_COOKIE}=""' in res.headers["set-cookie"] or "Max-Age=0" in res.headers["set-cookie"]
    assert (await logged_in.client.get("/api/auth/me")).status_code == 401


async def test_a_malformed_login_body_is_a_400(api: Api) -> None:
    res = await api.client.post("/api/auth/login", json={"user": "suporte"})
    assert (res.status_code, res.json()) == (400, {"detail": "Pedido inválido."})
    res = await api.client.post(
        "/api/auth/login",
        content="user=suporte&password=senha-de-teste",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert (res.status_code, res.json()) == (400, {"detail": "Pedido inválido."})


def test_safe_equal_compares_by_content() -> None:
    assert safe_equal("abc", "abc") is True
    assert safe_equal("abc", "abd") is False
    assert safe_equal("abc", "abcd") is False


async def test_api_docs_are_off_by_default(api: Api) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await api.client.get(path)).status_code == 404, path


async def test_api_docs_can_be_turned_on(h: Harness) -> None:
    app = create_app(replace(TEST_CONFIG, enable_api_docs=True), deps=h.deps, scheduler=RecordingScheduler())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 200, path
