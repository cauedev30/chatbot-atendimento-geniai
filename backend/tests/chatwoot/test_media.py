import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from geniai.app.ports import FetchFailure, ImageData, MediaFetcher
from geniai.chatwoot.http import ChatwootHttpConfig
from geniai.chatwoot.media import create_chatwoot_media
from tests.support.http import TrackedTransport

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PHOTO = "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/foto.png"
STORAGE = "https://storage.example/bucket/abc123?signature=xyz"


def fetcher(
    handler: Callable[[httpx.Request], httpx.Response | asyncio.Future[httpx.Response]],
    max_bytes: int = 1024,
    timeout_ms: int = 2000,
) -> tuple[MediaFetcher, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    async def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        result = handler(request)
        return await result if isinstance(result, asyncio.Future) else result

    cfg = ChatwootHttpConfig(
        base_url="https://chatwoot.example/", account_id=3, api_token="tok", transport=httpx.MockTransport(record)
    )
    return create_chatwoot_media(cfg, max_bytes=max_bytes, timeout_ms=timeout_ms), calls


def image(content: bytes = PNG, content_type: str = "image/png") -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": content_type})


async def fetch(
    handler: Callable[[httpx.Request], httpx.Response], url: str = PHOTO, **kw: int
) -> tuple[ImageData | FetchFailure, list[httpx.Request]]:
    media, calls = fetcher(handler, **kw)
    return await media.fetch_image(url), calls


async def test_downloads_an_image_from_chatwoot_with_the_token() -> None:
    result, calls = await fetch(lambda _: image(content_type="image/png; charset=binary"))
    assert result == ImageData(PNG, "image/png")
    assert str(calls[0].url) == PHOTO
    assert calls[0].headers["api_access_token"] == "tok"


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/rails/active_storage/blobs/redirect/abc123/foto.png",
        "http://chatwoot.example/rails/active_storage/blobs/redirect/abc123/foto.png",
        "https://chatwoot.example:8443/foto.png",
        "https://chatwoot.example.evil.example/foto.png",
        "ftp://chatwoot.example/foto.png",
        "/rails/active_storage/foto.png",
    ],
)
async def test_never_downloads_a_link_outside_the_configured_chatwoot(url: str) -> None:
    result, calls = await fetch(lambda _: image(), url=url)
    assert result == FetchFailure("host")
    assert calls == []


def redirect(location: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"location": location})


async def test_follows_a_redirect_to_the_storage_without_the_token() -> None:
    result, calls = await fetch(lambda r: redirect(STORAGE) if r.url.host == "chatwoot.example" else image())
    assert result == ImageData(PNG, "image/png")
    assert [r.url.host for r in calls] == ["chatwoot.example", "storage.example"]
    assert calls[0].headers["api_access_token"] == "tok"
    assert "api_access_token" not in calls[1].headers


async def test_keeps_the_token_on_a_relative_redirect_within_chatwoot() -> None:
    result, calls = await fetch(
        lambda r: redirect("/rails/other/foto.png") if r.url.path.endswith("abc123/foto.png") else image()
    )
    assert isinstance(result, ImageData)
    assert str(calls[1].url) == "https://chatwoot.example/rails/other/foto.png"
    assert calls[1].headers["api_access_token"] == "tok"


async def test_gives_up_after_three_redirects() -> None:
    result, calls = await fetch(lambda r: redirect(f"{STORAGE}&n={len(str(r.url))}"))
    assert result == FetchFailure("redirects")
    assert len(calls) == 4


async def test_refuses_a_redirect_that_drops_https() -> None:
    result, calls = await fetch(lambda _: redirect("http://storage.example/abc123"))
    assert result == FetchFailure("host")
    assert len(calls) == 1


@pytest.mark.parametrize("content_type", ["image/gif", "text/html", "application/octet-stream", ""])
async def test_refuses_anything_but_jpeg_png_or_webp(content_type: str) -> None:
    result, _ = await fetch(lambda _: image(content_type=content_type))
    assert result == FetchFailure("type", content_type or None, len(PNG))


@pytest.mark.parametrize("content_type", ["image/jpeg", "image/png", "image/webp", "IMAGE/JPEG"])
async def test_accepts_jpeg_png_and_webp(content_type: str) -> None:
    result, _ = await fetch(lambda _: image(content_type=content_type))
    assert result == ImageData(PNG, content_type.lower())


async def test_refuses_an_image_whose_declared_size_is_over_the_limit() -> None:
    result, _ = await fetch(lambda _: image(b"x" * 2000), max_bytes=1024)
    assert result == FetchFailure("size", "image/png", 2000)


async def test_stops_reading_an_undeclared_stream_once_it_passes_the_limit() -> None:
    sent: list[int] = []

    async def endless() -> AsyncIterator[bytes]:
        while True:
            sent.append(1)
            yield b"x" * 100

    result, _ = await fetch(lambda _: httpx.Response(200, content=endless(), headers={"content-type": "image/png"}))
    assert result == FetchFailure("size", "image/png")
    assert len(sent) <= 12


async def test_refuses_an_empty_image() -> None:
    result, _ = await fetch(lambda _: image(b""))
    assert result == FetchFailure("empty", "image/png", 0)


@pytest.mark.parametrize("status", [401, 404, 500, 502])
async def test_reports_a_chatwoot_failure(status: int) -> None:
    result, _ = await fetch(lambda _: httpx.Response(status))
    assert result == FetchFailure("status")


async def test_reports_a_connection_failure_without_raising() -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    result, _ = await fetch(refuse)
    assert result == FetchFailure("error")


async def test_gives_up_after_the_time_limit() -> None:
    def hang(_: httpx.Request) -> asyncio.Future[httpx.Response]:
        return asyncio.get_running_loop().create_future()

    media, _ = fetcher(hang, timeout_ms=20)
    assert await media.fetch_image(PHOTO) == FetchFailure("timeout")


async def test_reuses_one_client_without_carrying_the_token_or_cookies_to_the_storage() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "chatwoot.example":
            return httpx.Response(302, headers={"location": STORAGE, "set-cookie": "cw=1; Path=/"})
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png", "set-cookie": "st=1; Path=/"})

    transport = TrackedTransport(httpx.MockTransport(handle))
    cfg = ChatwootHttpConfig(base_url="https://chatwoot.example/", account_id=3, api_token="tok", transport=transport)
    media = create_chatwoot_media(cfg, max_bytes=1024, timeout_ms=2000)
    assert await media.fetch_image(PHOTO) == ImageData(PNG, "image/png")
    assert await media.fetch_image(PHOTO) == ImageData(PNG, "image/png")
    assert [r.url.host for r in calls] == ["chatwoot.example", "storage.example"] * 2
    assert [r.headers.get("api_access_token") for r in calls] == ["tok", None, "tok", None]
    assert all("cookie" not in r.headers for r in calls)
    assert transport.closed == 0
    await media.aclose()
    assert transport.closed == 1
