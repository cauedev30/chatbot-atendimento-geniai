import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest

from geniai.app.ports import LlmRequest
from geniai.llm.openai_compatible import OpenAiCompatibleConfig, create_openai_compatible_llm

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def recording_transport(handler: Handler) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    async def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return await handler(request)

    return httpx.MockTransport(record), calls


def completion(content: str | None) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def config(transport: httpx.MockTransport, extra_body: dict[str, object] | None = None) -> OpenAiCompatibleConfig:
    return OpenAiCompatibleConfig(
        base_url="https://llm.example/v1/",
        api_key="test-key",
        model="model-x",
        extra_body=extra_body,
        transport=transport,
    )


async def test_posts_a_json_mode_chat_completion_and_returns_the_content() -> None:
    async def ok(_: httpx.Request) -> httpx.Response:
        return completion('{"ok":true}')

    transport, calls = recording_transport(ok)
    llm = create_openai_compatible_llm(config(transport, {"thinking": {"type": "disabled"}}))
    assert await llm.complete(LlmRequest(system="sys", user="usr", timeout_ms=1000)) == '{"ok":true}'
    call = calls[0]
    assert str(call.url) == "https://llm.example/v1/chat/completions"
    assert call.method == "POST"
    assert call.headers["authorization"] == "Bearer test-key"
    assert call.headers["content-type"] == "application/json"
    assert json.loads(call.content) == {
        "model": "model-x",
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "thinking": {"type": "disabled"},
    }


async def test_throws_on_a_non_2xx_status() -> None:
    async def limited(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    transport, _ = recording_transport(limited)
    llm = create_openai_compatible_llm(config(transport))
    with pytest.raises(RuntimeError, match="429"):
        await llm.complete(LlmRequest(system="s", user="u", timeout_ms=1000))


async def test_throws_on_empty_content() -> None:
    async def empty(_: httpx.Request) -> httpx.Response:
        return completion(None)

    transport, _ = recording_transport(empty)
    llm = create_openai_compatible_llm(config(transport))
    with pytest.raises(RuntimeError, match="empty"):
        await llm.complete(LlmRequest(system="s", user="u", timeout_ms=1000))


async def test_aborts_after_the_timeout() -> None:
    async def hang(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return completion("{}")

    transport, _ = recording_transport(hang)
    llm = create_openai_compatible_llm(config(transport))
    with pytest.raises(TimeoutError):
        await llm.complete(LlmRequest(system="s", user="u", timeout_ms=20))
