import httpx


class TrackedTransport(httpx.AsyncBaseTransport):
    """Wraps a MockTransport and counts how many times a client closed it."""

    def __init__(self, inner: httpx.MockTransport) -> None:
        self._inner = inner
        self.closed = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        self.closed += 1
