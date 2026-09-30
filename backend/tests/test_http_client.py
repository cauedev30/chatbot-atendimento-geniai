import httpx

from geniai.http_client import KEEPALIVE_S, pooled_client
from tests.support.http import TrackedTransport


async def test_keeps_no_cookie_between_calls() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, headers={"set-cookie": "session=abc; Path=/"})

    client = pooled_client(httpx.MockTransport(handle), timeout=1.0)
    await client.get("https://storage.example/a")
    await client.get("https://storage.example/b")
    await client.aclose()
    assert "cookie" not in calls[1].headers


async def test_follows_no_redirect_by_itself() -> None:
    client = pooled_client(httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "/x"})), timeout=1.0)
    res = await client.get("https://chatwoot.example/a")
    await client.aclose()
    assert res.status_code == 302


async def test_closes_its_transport_only_when_closed() -> None:
    transport = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200)))
    client = pooled_client(transport, timeout=1.0)
    await client.get("https://llm.example/a")
    await client.get("https://llm.example/b")
    assert transport.closed == 0
    await client.aclose()
    assert transport.closed == 1


async def test_keeps_an_idle_connection_open_between_the_turns_of_a_conversation() -> None:
    # httpx's default (5 s) drops it before a customer answers, even after the 4-5 s burst window.
    client = pooled_client(None, timeout=1.0)
    assert client._transport._pool._keepalive_expiry == KEEPALIVE_S == 50  # type: ignore[attr-defined]
    await client.aclose()
