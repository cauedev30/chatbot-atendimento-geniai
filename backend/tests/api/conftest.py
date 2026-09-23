from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from geniai.api.auth import AuthConfig
from geniai.app.keyed_queue import KeyedQueue
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.http import ChatwootHttpConfig
from geniai.config import AppConfig
from geniai.domain.rules import DEFAULT_RULES
from geniai.llm.openai_compatible import OpenAiCompatibleConfig
from geniai.main import create_app
from tests.conftest import Harness

WEBHOOK_TOKEN = "token-de-teste-123456"
TEST_CONFIG = AppConfig(
    database_url="postgresql://unused",
    port=8000,
    host="127.0.0.1",
    webhook_token=WEBHOOK_TOKEN,
    chatwoot=ChatwootHttpConfig(base_url="https://chatwoot.example", account_id=1, api_token="tok"),
    llm=OpenAiCompatibleConfig(base_url="https://llm.example/v1", api_key="key", model="model-x"),
    auth=AuthConfig(
        user="suporte",
        password="senha-de-teste",
        cookie_secret="segredo-de-teste-com-mais-de-32-caracteres",
        secure_cookie=False,
    ),
    rules=DEFAULT_RULES,
)


class Api:
    """The app wired to the test harness, with an HTTP client and a logged-in helper."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.scheduler = RecordingScheduler()
        self.app: FastAPI = create_app(TEST_CONFIG, deps=h.deps, scheduler=self.scheduler, queue=KeyedQueue())
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def login(self) -> None:
        res = await self.client.post("/api/auth/login", json={"user": "suporte", "password": "senha-de-teste"})
        assert res.status_code == 204, res.text


@pytest.fixture
async def api(h: Harness) -> AsyncIterator[Api]:
    a = Api(h)
    yield a
    await a.client.aclose()


@pytest.fixture
async def logged_in(api: Api) -> Api:
    await api.login()
    return api
