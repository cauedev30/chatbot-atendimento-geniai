import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from geniai.app.ports import AudioData, TranscribeFailure
from geniai.transcription.openai_compatible import (
    OpenAiCompatibleTranscriber,
    TranscriberConfig,
    create_openai_compatible_transcriber,
)
from tests.support.http import TrackedTransport

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]
VOICE = AudioData(b"OggS-voice-bytes", "audio/ogg", 12.5)


def transcriber(handler: Handler, timeout_ms: int = 2000) -> tuple[OpenAiCompatibleTranscriber, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    async def record(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append(request)
        return await handler(request)

    cfg = TranscriberConfig(
        base_url="https://stt.example/v1/", api_key="stt-key", model="stt-model", transport=httpx.MockTransport(record)
    )
    return create_openai_compatible_transcriber(cfg, timeout_ms=timeout_ms), calls


async def transcribe(
    handler: Handler, audio: AudioData = VOICE, **kw: int
) -> tuple[str | TranscribeFailure, list[httpx.Request]]:
    t, calls = transcriber(handler, **kw)
    return await t.transcribe(audio), calls


def answer(text: object, status: int = 200) -> Handler:
    async def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"text": text})

    return handle


async def test_posts_the_audio_as_multipart_in_portuguese_and_returns_the_text() -> None:
    result, [call] = await transcribe(answer("  meu número caiu  "))
    assert result == "meu número caiu"
    assert (call.method, str(call.url)) == ("POST", "https://stt.example/v1/audio/transcriptions")
    assert call.headers["authorization"] == "Bearer stt-key"
    assert call.headers["content-type"].startswith("multipart/form-data")
    body = call.content
    assert b'name="model"\r\n\r\nstt-model\r\n' in body
    assert b'name="language"\r\n\r\npt\r\n' in body
    assert b'name="file"; filename="audio.ogg"\r\nContent-Type: audio/ogg\r\n\r\nOggS-voice-bytes\r\n' in body


@pytest.mark.parametrize(("content_type", "name"), [("audio/mpeg", "audio.mp3"), ("audio/x-m4a", "audio.m4a")])
async def test_names_the_file_by_an_extension_the_api_recognizes(content_type: str, name: str) -> None:
    _, [call] = await transcribe(answer("ok"), AudioData(b"x", content_type, None))
    assert f'filename="{name}"'.encode() in call.content


@pytest.mark.parametrize("text", ["", "   \n "])
async def test_an_empty_transcription_is_a_failure(text: str) -> None:
    result, _ = await transcribe(answer(text))
    assert result == TranscribeFailure("empty")


@pytest.mark.parametrize("status", [400, 401, 413, 429, 500])
async def test_reports_a_provider_failure_by_its_status(status: int) -> None:
    result, _ = await transcribe(answer("x", status))
    assert result == TranscribeFailure("status", status)


@pytest.mark.parametrize("body", [{"texto": "x"}, {"text": 42}, ["x"]])
async def test_reports_an_unexpected_answer_without_raising(body: object) -> None:
    async def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    result, _ = await transcribe(handle)
    assert result == TranscribeFailure("error")


async def test_reports_a_connection_failure_without_raising() -> None:
    async def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result, _ = await transcribe(refuse)
    assert result == TranscribeFailure("error")


async def test_gives_up_after_the_time_limit() -> None:
    async def hang(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200)

    result, _ = await transcribe(hang, timeout_ms=20)
    assert result == TranscribeFailure("timeout")


async def test_keeps_one_client_until_closed() -> None:
    transport = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200, json={"text": "oi"})))
    cfg = TranscriberConfig(base_url="https://stt.example/v1", api_key="k", model="m", transport=transport)
    t = create_openai_compatible_transcriber(cfg, timeout_ms=2000)
    assert [await t.transcribe(VOICE), await t.transcribe(VOICE)] == ["oi", "oi"]
    assert transport.closed == 0
    await t.aclose()
    assert transport.closed == 1
