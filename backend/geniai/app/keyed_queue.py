import asyncio
from collections.abc import Awaitable, Callable


class KeyedQueue:
    """Serializes async tasks per key, in process. Every webhook and every turn of one Chatwoot
    conversation runs under the same key, so the ticket of a conversation is never raced."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._users: dict[str, int] = {}

    async def run[T](self, key: str, task: Callable[[], Awaitable[T]]) -> T:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            async with lock:  # asyncio.Lock wakes waiters in FIFO order
                return await task()
        finally:
            self._users[key] -= 1
            if self._users[key] == 0:
                del self._users[key]
                del self._locks[key]


def conversation_key(conversation_id: int) -> str:
    return f"conversation:{conversation_id}"
