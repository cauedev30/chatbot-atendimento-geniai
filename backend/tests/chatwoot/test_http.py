import json

import httpx
import pytest

from geniai.chatwoot.http import REQUEST_TIMEOUT, ChatwootHttpConfig, create_chatwoot_http


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


def scripted_transport(steps: list[int | Exception]) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Each call takes the next step: a status code to answer, or an exception to raise."""
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        step = steps.pop(0) if steps else 200
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, json={})

    return httpx.MockTransport(handle), calls


@pytest.mark.parametrize("first", [502, 503, 504])
async def test_retries_a_gateway_answer_the_chatwoot_app_never_saw(first: int) -> None:
    transport, calls = scripted_transport([first, 200])
    await create_chatwoot_http(cfg(transport)).send_message(45, "olá")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("refused"), httpx.ConnectTimeout("no connection"), httpx.PoolTimeout("pool")]
)
async def test_retries_when_the_request_never_left(error: Exception) -> None:
    transport, calls = scripted_transport([error, 200])
    await create_chatwoot_http(cfg(transport)).send_message(45, "olá")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("slow"), httpx.WriteTimeout("slow"), httpx.RemoteProtocolError("x")]
)
async def test_never_repeats_a_post_that_may_have_been_processed(error: Exception) -> None:
    # A message sent twice reaches the customer twice: after a read timeout, give up.
    transport, calls = scripted_transport([error, 200])
    with pytest.raises(type(error)):
        await create_chatwoot_http(cfg(transport)).send_message(45, "olá")
    assert len(calls) == 1


@pytest.mark.parametrize("status", [400, 401, 404, 422, 500])
async def test_never_repeats_after_another_answer(status: int) -> None:
    transport, calls = scripted_transport([status, 200])
    with pytest.raises(RuntimeError, match=str(status)):
        await create_chatwoot_http(cfg(transport)).send_message(45, "olá")
    assert len(calls) == 1


async def test_throws_after_the_last_retry() -> None:
    transport, calls = scripted_transport([503, 503, 503])
    with pytest.raises(RuntimeError, match="503"):
        await create_chatwoot_http(cfg(transport, retries=2)).send_message(45, "olá")
    assert len(calls) == 3


def test_waits_30_s_for_an_answer() -> None:
    assert REQUEST_TIMEOUT.read == 30
    assert REQUEST_TIMEOUT.connect is not None and REQUEST_TIMEOUT.connect <= 10
