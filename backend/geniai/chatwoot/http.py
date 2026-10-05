import asyncio
from dataclasses import dataclass

import httpx

from geniai.app.ports import ChatwootMessage, ChatwootStatus
from geniai.chatwoot.messages import parse_conversation_messages
from geniai.http_client import pooled_client

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


class ChatwootHttp:
    """Keeps one HTTP client, and so its connections, until aclose() (see main.py)."""

    def __init__(self, cfg: ChatwootHttpConfig) -> None:
        self._cfg = cfg
        self._base = cfg.base_url.rstrip("/")
        self._client = pooled_client(cfg.transport, timeout=REQUEST_TIMEOUT)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _conversation_path(self, conversation_id: int) -> str:
        return f"{self._base}/api/v1/accounts/{self._cfg.account_id}/conversations/{conversation_id}"

    async def _post(self, url: str, body: dict[str, object]) -> httpx.Response:
        """POSTs are not idempotent: a message repeated after Chatwoot processed it reaches the customer
        twice. So a call is repeated only when it surely was not processed (connection failures and
        gateway answers 502/503/504); a read timeout or any other answer ends it at once."""
        for attempt in range(self._cfg.retries + 1):
            if attempt > 0:
                await asyncio.sleep(self._cfg.retry_delay_ms * attempt / 1000)
            last = attempt == self._cfg.retries
            try:
                res = await self._client.post(url, json=body, headers={"api_access_token": self._cfg.api_token})
            except NOT_SENT:
                if last:
                    raise
                continue
            if res.is_success:
                return res
            retryable = res.status_code in RETRYABLE_STATUS
            if not retryable or last:
                raise ChatwootError(f"Chatwoot HTTP {res.status_code} on {url}", retryable=retryable)
        raise AssertionError("unreachable")

    async def send_message(self, conversation_id: int, text: str) -> int | None:
        body: dict[str, object] = {"content": text, "message_type": "outgoing", "private": False}
        res = await self._post(f"{self._conversation_path(conversation_id)}/messages", body)
        try:
            sent = res.json()
        except ValueError:
            return None
        message_id = sent.get("id") if isinstance(sent, dict) else None
        return message_id if isinstance(message_id, int) and not isinstance(message_id, bool) else None

    async def list_messages(self, conversation_id: int) -> list[ChatwootMessage]:
        """One attempt, with the client's time limits: the caller carries on without the answer."""
        url = f"{self._conversation_path(conversation_id)}/messages"
        res = await self._client.get(url, headers={"api_access_token": self._cfg.api_token})
        if not res.is_success:
            raise ChatwootError(f"Chatwoot HTTP {res.status_code} on {url}", retryable=False)
        return parse_conversation_messages(res.json())

    async def send_private_note(self, conversation_id: int, text: str) -> None:
        """A note for the team in the conversation; the customer never sees it."""
        body: dict[str, object] = {"content": text, "message_type": "outgoing", "private": True}
        await self._post(f"{self._conversation_path(conversation_id)}/messages", body)

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None:
        await self._post(f"{self._conversation_path(conversation_id)}/toggle_status", {"status": status})

    def conversation_url(self, conversation_id: int) -> str:
        return f"{self._base}/app/accounts/{self._cfg.account_id}/conversations/{conversation_id}"


def create_chatwoot_http(cfg: ChatwootHttpConfig) -> ChatwootHttp:
    return ChatwootHttp(cfg)
