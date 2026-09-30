"""Downloads a customer's image from Chatwoot for the turn (see app/process_turn.py)."""

import asyncio
from typing import Final
from urllib.parse import urljoin, urlsplit

import httpx

from geniai.app.ports import FetchFailure, ImageData, MediaFetcher
from geniai.chatwoot.http import ChatwootHttpConfig

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


class _ChatwootMedia:
    """Only a link on the configured Chatwoot (same scheme, host and port) is downloaded. The API token
    goes only to that origin: Chatwoot's file links usually redirect to the storage, another host, which
    gets no token. At most MAX_REDIRECTS redirects, never from https to http. The size is read as a
    stream and the download stops once it passes the limit; the whole download has one time limit."""

    def __init__(self, cfg: ChatwootHttpConfig, max_bytes: int, timeout_ms: int) -> None:
        self._cfg = cfg
        self._chatwoot = _origin(cfg.base_url)
        self._max_bytes = max_bytes
        self._timeout_s = timeout_ms / 1000

    async def fetch_image(self, url: str) -> ImageData | FetchFailure:
        if self._chatwoot is None or _origin(url) != self._chatwoot:
            return FetchFailure("host")
        try:
            async with (
                asyncio.timeout(self._timeout_s),
                httpx.AsyncClient(transport=self._cfg.transport, timeout=self._timeout_s) as client,
            ):
                return await self._follow(client, url)
        except (TimeoutError, httpx.TimeoutException):
            return FetchFailure("timeout")
        except Exception:
            return FetchFailure("error")

    async def _follow(self, client: httpx.AsyncClient, url: str) -> ImageData | FetchFailure:
        for _ in range(MAX_REDIRECTS + 1):
            origin = _origin(url)
            headers = {"api_access_token": self._cfg.api_token} if origin == self._chatwoot else {}
            async with client.stream("GET", url, headers=headers) as res:
                if not res.is_redirect:
                    return await self._read(res)
                url = urljoin(url, res.headers["location"])
                target = _origin(url)
                if target is None or (origin is not None and origin[0] == "https" and target[0] != "https"):
                    return FetchFailure("host")
        return FetchFailure("redirects")

    async def _read(self, res: httpx.Response) -> ImageData | FetchFailure:
        if not res.is_success:
            return FetchFailure("status")
        content_type = res.headers.get("content-type", "").split(";")[0].strip().lower()
        declared = _declared_size(res)
        if content_type not in ACCEPTED_IMAGE_TYPES:
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
        return ImageData(bytes(data), content_type)


def create_chatwoot_media(cfg: ChatwootHttpConfig, *, max_bytes: int, timeout_ms: int) -> MediaFetcher:
    return _ChatwootMedia(cfg, max_bytes, timeout_ms)
