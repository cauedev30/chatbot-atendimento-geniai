"""Downloads a customer's image or audio from Chatwoot for the turn (see app/process_turn.py)."""

import asyncio
from collections.abc import Collection
from typing import Final
from urllib.parse import urljoin, urlsplit

import httpx

from geniai.app.ports import AudioData, FetchFailure, ImageData
from geniai.audio import AUDIO_FORMATS, audio_seconds
from geniai.chatwoot.http import ChatwootHttpConfig
from geniai.http_client import pooled_client

ACCEPTED_IMAGE_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_REDIRECTS: Final = 3

Origin = tuple[str, str, int]


def _origin(url: str) -> Origin | None:
    """Scheme, host and port of an absolute http(s) link; None for anything else."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    return scheme, parts.hostname.lower(), port or (443 if scheme == "https" else 80)


def _declared_size(res: httpx.Response) -> int | None:
    raw = res.headers.get("content-length")
    return int(raw) if raw is not None and raw.isdigit() else None


class ChatwootMedia:
    """Only a link on the configured Chatwoot (same scheme, host and port) is downloaded. The API token
    goes only to that origin: Chatwoot's file links usually redirect to the storage, another host, which
    gets no token. At most MAX_REDIRECTS redirects, never from https to http. The size is read as a
    stream and the download stops once it passes the limit; the whole download has one time limit.

    Keeps one HTTP client until aclose() (see main.py). The token is never one of its default headers:
    each request carries it only when it goes to Chatwoot (see _follow)."""

    def __init__(self, cfg: ChatwootHttpConfig, max_bytes: int, timeout_ms: int) -> None:
        self._cfg = cfg
        self._chatwoot = _origin(cfg.base_url)
        self._max_bytes = max_bytes
        self._timeout_s = timeout_ms / 1000
        self._client = pooled_client(cfg.transport, timeout=self._timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_image(self, url: str) -> ImageData | FetchFailure:
        got = await self._fetch(url, ACCEPTED_IMAGE_TYPES)
        return got if isinstance(got, FetchFailure) else ImageData(*got)

    async def fetch_audio(self, url: str) -> AudioData | FetchFailure:
        """Accepts the formats the transcription API takes (geniai.audio.AUDIO_FORMATS) and reads how long
        an Ogg Opus audio lasts."""
        got = await self._fetch(url, AUDIO_FORMATS.keys())
        if isinstance(got, FetchFailure):
            return got
        data, content_type = got
        return AudioData(data, content_type, audio_seconds(data, content_type))

    async def _fetch(self, url: str, accepted: Collection[str]) -> tuple[bytes, str] | FetchFailure:
        if self._chatwoot is None or _origin(url) != self._chatwoot:
            return FetchFailure("host")
        try:
            async with asyncio.timeout(self._timeout_s):
                return await self._follow(url, accepted)
        except (TimeoutError, httpx.TimeoutException):
            return FetchFailure("timeout")
        except Exception:
            return FetchFailure("error")

    async def _follow(self, url: str, accepted: Collection[str]) -> tuple[bytes, str] | FetchFailure:
        for _ in range(MAX_REDIRECTS + 1):
            origin = _origin(url)
            headers = {"api_access_token": self._cfg.api_token} if origin == self._chatwoot else {}
            async with self._client.stream("GET", url, headers=headers) as res:
                if not res.is_redirect:
                    return await self._read(res, accepted)
                url = urljoin(url, res.headers["location"])
                target = _origin(url)
                if target is None or (origin is not None and origin[0] == "https" and target[0] != "https"):
                    return FetchFailure("host")
        return FetchFailure("redirects")

    async def _read(self, res: httpx.Response, accepted: Collection[str]) -> tuple[bytes, str] | FetchFailure:
        if not res.is_success:
            return FetchFailure("status")
        content_type = res.headers.get("content-type", "").split(";")[0].strip().lower()
        declared = _declared_size(res)
        if content_type not in accepted:
            return FetchFailure("type", content_type or None, declared)
        if declared is not None and declared > self._max_bytes:
            return FetchFailure("size", content_type, declared)
        data = bytearray()
        async for chunk in res.aiter_bytes():
            data.extend(chunk)
            if len(data) > self._max_bytes:
                return FetchFailure("size", content_type)
        if not data:
            return FetchFailure("empty", content_type, 0)
        return bytes(data), content_type


def create_chatwoot_media(cfg: ChatwootHttpConfig, *, max_bytes: int, timeout_ms: int) -> ChatwootMedia:
    return ChatwootMedia(cfg, max_bytes, timeout_ms)
