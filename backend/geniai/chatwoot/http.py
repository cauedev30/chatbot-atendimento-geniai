import asyncio
from dataclasses import dataclass

import httpx

from geniai.app.ports import ChatwootPort, ChatwootStatus

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

RETRYABLE_STATUS = frozenset({502, 503, 504})
"""Answers from a gateway in front of Chatwoot: the request did not reach the app."""

NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
"""Failures before the request left: repeating it cannot duplicate anything."""


class ChatwootError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ChatwootHttpConfig:
    base_url: str
    account_id: int
    api_token: str
    transport: httpx.AsyncBaseTransport | None = None
    """Tests pass an httpx.MockTransport."""
    retries: int = 2
    """Extra attempts after the first one, only when the request surely was not processed (spec §10)."""
    retry_delay_ms: int = 1000


class _ChatwootHttp:
    def __init__(self, cfg: ChatwootHttpConfig) -> None:
        self._cfg = cfg
        self._base = cfg.base_url.rstrip("/")

    def _conversation_path(self, conversation_id: int) -> str:
        return f"{self._base}/api/v1/accounts/{self._cfg.account_id}/conversations/{conversation_id}"

    async def _post(self, url: str, body: dict[str, object]) -> None:
        """POSTs are not idempotent: a message repeated after Chatwoot processed it reaches the customer
        twice. So a call is repeated only when it surely was not processed (connection failures and
        gateway answers 502/503/504); a read timeout or any other answer ends it at once."""
        async with httpx.AsyncClient(transport=self._cfg.transport, timeout=REQUEST_TIMEOUT) as client:
            for attempt in range(self._cfg.retries + 1):
                if attempt > 0:
                    await asyncio.sleep(self._cfg.retry_delay_ms * attempt / 1000)
                last = attempt == self._cfg.retries
                try:
                    res = await client.post(url, json=body, headers={"api_access_token": self._cfg.api_token})
                except NOT_SENT:
                    if last:
                        raise
                    continue
                if res.is_success:
                    return
                retryable = res.status_code in RETRYABLE_STATUS
                if not retryable or last:
                    raise ChatwootError(f"Chatwoot HTTP {res.status_code} on {url}", retryable=retryable)

    async def send_message(self, conversation_id: int, text: str) -> None:
        body: dict[str, object] = {"content": text, "message_type": "outgoing", "private": False}
        await self._post(f"{self._conversation_path(conversation_id)}/messages", body)

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None:
        await self._post(f"{self._conversation_path(conversation_id)}/toggle_status", {"status": status})

    def conversation_url(self, conversation_id: int) -> str:
        return f"{self._base}/app/accounts/{self._cfg.account_id}/conversations/{conversation_id}"


def create_chatwoot_http(cfg: ChatwootHttpConfig) -> ChatwootPort:
    return _ChatwootHttp(cfg)
