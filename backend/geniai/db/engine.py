from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def to_async_url(url: str) -> str:
    """`postgresql://` and `postgres://` URLs select the asyncpg driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def create_engine(url: str, **kw: Any) -> AsyncEngine:
    return create_async_engine(to_async_url(url), **kw)
