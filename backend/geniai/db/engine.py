from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

SSL_MODES: Final = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
"""libpq's sslmode values; asyncpg takes the same names through its `ssl` argument."""


def to_async_url(url: str) -> str:
    """`postgresql://` and `postgres://` URLs select the asyncpg driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def asyncpg_connect_args(url: str) -> tuple[str, dict[str, Any]]:
    """The asyncpg URL and connect arguments for a libpq-style URL: `sslmode=...`, which asyncpg does
    not accept in the query string, becomes its `ssl` argument."""
    parts = urlsplit(to_async_url(url))
    query = parse_qsl(parts.query, keep_blank_values=True)
    args: dict[str, Any] = {}
    kept = []
    for key, value in query:
        if key == "sslmode":
            if value not in SSL_MODES:
                raise ValueError(f"unknown sslmode {value!r}; use one of {', '.join(sorted(SSL_MODES))}")
            args["ssl"] = value
        else:
            kept.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(kept))), args


def create_engine(url: str, **kw: Any) -> AsyncEngine:
    async_url, ssl_args = asyncpg_connect_args(url)
    connect_args = {**ssl_args, **kw.pop("connect_args", {})}
    return create_async_engine(async_url, connect_args=connect_args, **kw)
