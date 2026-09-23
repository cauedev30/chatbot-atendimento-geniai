import asyncio
from dataclasses import dataclass

import httpx

from geniai.app.ports import ChatwootPort, ChatwootStatus

REQUEST_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class ChatwootHttpConfig:
    base_url: str
    account_id: int
    api_token: str
    transport: httpx.AsyncBaseTransport | None = None
    """Tests pass an httpx.MockTransport."""
    retries: int = 2
    """Extra attempts after the first one (spec §10: "retried a few times")."""
    retry_delay_ms: int = 1000


class _ChatwootHttp:
    def __init__(self, cfg: ChatwootHttpConfig) -> None:
        self._cfg = cfg
        self._base = cfg.base_url.rstrip("/")

    def _conversation_path(self, conversation_id: int) -> str:
        return f"{self._base}/api/v1/accounts/{self._cfg.account_id}/conversations/{conversation_id}"

    async def _post(self, url: str, body: dict[str, object]) -> None:
        last_error: Exception = RuntimeError(f"Chatwoot call not attempted: {url}")
        async with httpx.AsyncClient(transport=self._cfg.transport, timeout=REQUEST_TIMEOUT_S) as client:
            for attempt in range(self._cfg.retries + 1):
                if attempt > 0:
                    await asyncio.sleep(self._cfg.retry_delay_ms * attempt / 1000)
                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT_S):
                        res = await client.post(url, json=body, headers={"api_access_token": self._cfg.api_token})
                    if res.is_success:
                        return
                    last_error = RuntimeError(f"Chatwoot HTTP {res.status_code} on {url}")
                except Exception as err:
                    last_error = err
        raise last_error

    async def send_message(self, conversation_id: int, text: str) -> None:
        body: dict[str, object] = {"content": text, "message_type": "outgoing", "private": False}
        await self._post(f"{self._conversation_path(conversation_id)}/messages", body)

    async def set_status(self, conversation_id: int, status: ChatwootStatus) -> None:
        await self._post(f"{self._conversation_path(conversation_id)}/toggle_status", {"status": status})

    def conversation_url(self, conversation_id: int) -> str:
        return f"{self._base}/app/accounts/{self._cfg.account_id}/conversations/{conversation_id}"


def create_chatwoot_http(cfg: ChatwootHttpConfig) -> ChatwootPort:
    return _ChatwootHttp(cfg)
