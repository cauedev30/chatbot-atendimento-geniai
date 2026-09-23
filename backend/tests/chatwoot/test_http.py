import json

import httpx
import pytest

from geniai.chatwoot.http import ChatwootHttpConfig, create_chatwoot_http


def recording_transport(statuses: list[int]) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(statuses.pop(0) if statuses else 200, json={})

    return httpx.MockTransport(handle), calls


def cfg(transport: httpx.MockTransport | None = None, retries: int = 2) -> ChatwootHttpConfig:
    return ChatwootHttpConfig(
        base_url="https://chatwoot.example/",
        account_id=3,
        api_token="tok",
        transport=transport,
        retries=retries,
        retry_delay_ms=0,
    )


async def test_sends_an_outgoing_message() -> None:
    transport, calls = recording_transport([200])
    await create_chatwoot_http(cfg(transport)).send_message(45, "olá")
    assert str(calls[0].url) == "https://chatwoot.example/api/v1/accounts/3/conversations/45/messages"
    assert calls[0].headers["api_access_token"] == "tok"
    assert json.loads(calls[0].content) == {"content": "olá", "message_type": "outgoing", "private": False}


async def test_toggles_the_conversation_status() -> None:
    transport, calls = recording_transport([200])
    await create_chatwoot_http(cfg(transport)).set_status(45, "open")
    assert str(calls[0].url) == "https://chatwoot.example/api/v1/accounts/3/conversations/45/toggle_status"
    assert json.loads(calls[0].content) == {"status": "open"}


def test_builds_the_conversation_link() -> None:
    assert (
        create_chatwoot_http(cfg()).conversation_url(45) == "https://chatwoot.example/app/accounts/3/conversations/45"
    )


async def test_retries_failures_and_then_succeeds() -> None:
    transport, calls = recording_transport([502, 503, 200])
    await create_chatwoot_http(cfg(transport, retries=2)).send_message(45, "olá")
    assert len(calls) == 3


async def test_throws_after_the_last_retry() -> None:
    transport, calls = recording_transport([500, 500, 500])
    with pytest.raises(RuntimeError, match="500"):
        await create_chatwoot_http(cfg(transport, retries=2)).send_message(45, "olá")
    assert len(calls) == 3
