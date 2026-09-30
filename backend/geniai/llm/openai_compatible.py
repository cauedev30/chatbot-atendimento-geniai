import asyncio
import base64
from dataclasses import dataclass
from typing import Annotated

import httpx
from pydantic import BaseModel, Field

from geniai.app.ports import ImageData, LlmRequest
from geniai.http_client import pooled_client


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


def _data_uri(image: ImageData) -> str:
    return f"data:{image.content_type};base64,{base64.b64encode(image.data).decode('ascii')}"


def _user_content(request: LlmRequest) -> str | list[dict[str, object]]:
    """Plain text without images; with them, the text then each image as a data URI (some providers,
    Ollama among them, do not fetch image links)."""
    if not request.images:
        return request.user
    parts: list[dict[str, object]] = [{"type": "text", "text": request.user}]
    parts += [{"type": "image_url", "image_url": {"url": _data_uri(image)}} for image in request.images]
    return parts


class OpenAiCompatibleLlm:
    """Keeps one HTTP client, and so its connections, until aclose() (see main.py)."""

    def __init__(self, cfg: OpenAiCompatibleConfig) -> None:
        self._cfg = cfg
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        # Each call passes its own time limit.
        self._client = pooled_client(cfg.transport, timeout=httpx.Timeout(None))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, request: LlmRequest) -> str:
        body: dict[str, object] = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": _user_content(request)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            **(self._cfg.extra_body or {}),
        }
        timeout_s = request.timeout_ms / 1000
        # asyncio.timeout bounds the whole call (connect, send and read), not each step.
        async with asyncio.timeout(timeout_s):
            try:
                res = await self._client.post(
                    self._url,
                    json=body,
                    headers={"authorization": f"Bearer {self._cfg.api_key}"},
                    timeout=timeout_s,
                )
            except httpx.TimeoutException as err:
                # The same time limit, reached by httpx first: one kind of error for the caller.
                raise TimeoutError(str(err)) from err
            if not res.is_success:
                raise RuntimeError(f"LLM HTTP {res.status_code}: {res.text[:200]}")
            content = _Completion.model_validate(res.json()).choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content


def create_openai_compatible_llm(cfg: OpenAiCompatibleConfig) -> OpenAiCompatibleLlm:
    return OpenAiCompatibleLlm(cfg)
