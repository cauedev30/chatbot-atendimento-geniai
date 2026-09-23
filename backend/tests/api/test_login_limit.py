from dataclasses import replace
from ipaddress import ip_network

import httpx

from geniai.api.login_limit import LOGIN_MAX_FAILURES, TOO_MANY_ATTEMPTS, LoginLimiter, client_ip
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.main import create_app
from tests.api.conftest import TEST_CONFIG, Api
from tests.conftest import Harness

LOCAL = (ip_network("127.0.0.1/32"),)
WRONG = {"user": "suporte", "password": "errada"}
RIGHT = {"user": "suporte", "password": "senha-de-teste"}


def test_the_client_is_the_peer_unless_the_peer_is_a_trusted_proxy() -> None:
    assert client_ip("198.51.100.4", "203.0.113.1", LOCAL) == "198.51.100.4"
    assert client_ip("127.0.0.1", "203.0.113.1", LOCAL) == "203.0.113.1"
    assert client_ip("127.0.0.1", None, LOCAL) == "127.0.0.1"
    assert client_ip(None, None, LOCAL) == "unknown"


def test_takes_the_rightmost_forwarded_address_that_is_not_a_trusted_proxy() -> None:
    # A client can put anything on the left; the proxies in front append what they saw.
    assert client_ip("127.0.0.1", "198.51.100.7, 203.0.113.1", LOCAL) == "203.0.113.1"
    assert client_ip("127.0.0.1", "203.0.113.1, 127.0.0.1", LOCAL) == "203.0.113.1"
    proxies = (*LOCAL, ip_network("10.0.0.0/8"))
    assert client_ip("127.0.0.1", "203.0.113.1, 10.1.2.3", proxies) == "203.0.113.1"
    assert client_ip("127.0.0.1", "lixo", LOCAL) == "lixo"


def test_blocks_after_too_many_failures_within_the_window_then_forgets_them() -> None:
    now = [0.0]
    limiter = LoginLimiter(max_failures=3, window_s=60, clock=lambda: now[0])
    for _ in range(3):
        assert not limiter.blocked("a")
        limiter.fail("a")
    assert limiter.blocked("a")
    assert not limiter.blocked("b")
    now[0] = 61
    assert not limiter.blocked("a")


def test_a_successful_login_clears_the_failures() -> None:
    limiter = LoginLimiter(max_failures=2, window_s=60)
    limiter.fail("a")
    limiter.succeed("a")
    limiter.fail("a")
    assert not limiter.blocked("a")


async def login(api: Api, body: dict[str, str], forwarded_for: str) -> httpx.Response:
    return await api.client.post("/api/auth/login", json=body, headers={"x-forwarded-for": forwarded_for})


async def test_answers_429_to_an_address_with_too_many_failures_and_not_to_others(api: Api) -> None:
    for _ in range(LOGIN_MAX_FAILURES):
        assert (await login(api, WRONG, "203.0.113.1")).status_code == 401
    res = await login(api, RIGHT, "203.0.113.1")
    assert (res.status_code, res.json()) == (429, {"detail": TOO_MANY_ATTEMPTS})
    assert (await login(api, RIGHT, "203.0.113.2")).status_code == 204


async def test_a_forged_forwarded_address_does_not_escape_the_limit(api: Api) -> None:
    for i in range(LOGIN_MAX_FAILURES):
        await login(api, WRONG, f"198.51.100.{i}, 203.0.113.1")
    assert (await login(api, RIGHT, "198.51.100.200, 203.0.113.1")).status_code == 429


async def test_ignores_forwarded_addresses_from_an_untrusted_peer(h: Harness) -> None:
    app = create_app(replace(TEST_CONFIG, trusted_proxies=()), deps=h.deps, scheduler=RecordingScheduler())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for i in range(LOGIN_MAX_FAILURES):
            await client.post("/api/auth/login", json=WRONG, headers={"x-forwarded-for": f"203.0.113.{i}"})
        res = await client.post("/api/auth/login", json=RIGHT, headers={"x-forwarded-for": "203.0.113.99"})
    assert res.status_code == 429
