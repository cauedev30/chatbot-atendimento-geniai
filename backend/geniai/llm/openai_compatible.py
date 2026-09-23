import asyncio
from dataclasses import dataclass
from typing import Annotated

import httpx
from pydantic import BaseModel, Field

from geniai.app.ports import LlmPort, LlmRequest


@dataclass(frozen=True)
class OpenAiCompatibleConfig:
    base_url: str
    api_key: str
    model: str
    extra_body: dict[str, object] | None = None
    """Provider-specific fields merged into the body (e.g. to turn reasoning off)."""
    transport: httpx.AsyncBaseTransport | None = None
    """Tests pass an httpx.MockTransport."""


class _Message(BaseModel):
    content: str | None


class _Choice(BaseModel):
    message: _Message


class _Completion(BaseModel):
    choices: Annotated[list[_Choice], Field(min_length=1)]


class _OpenAiCompatibleLlm:
    def __init__(self, cfg: OpenAiCompatibleConfig) -> None:
        self._cfg = cfg
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"

    async def complete(self, request: LlmRequest) -> str:
        body: dict[str, object] = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            **(self._cfg.extra_body or {}),
        }
        timeout_s = request.timeout_ms / 1000
        # asyncio.timeout bounds the whole call (connect, send and read), not each step.
        async with asyncio.timeout(timeout_s), httpx.AsyncClient(transport=self._cfg.transport) as client:
            res = await client.post(
                self._url,
                json=body,
                headers={"authorization": f"Bearer {self._cfg.api_key}"},
                timeout=timeout_s,
            )
            if not res.is_success:
                raise RuntimeError(f"LLM HTTP {res.status_code}: {res.text[:200]}")
            content = _Completion.model_validate(res.json()).choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content


def create_openai_compatible_llm(cfg: OpenAiCompatibleConfig) -> LlmPort:
    return _OpenAiCompatibleLlm(cfg)
