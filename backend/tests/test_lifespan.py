from dataclasses import replace

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from geniai.config import load_config
from geniai.main import create_app
from tests.api.test_config import VALID
from tests.support.http import TrackedTransport


async def test_keeps_the_http_clients_open_while_running_and_closes_them_on_shutdown(
    engine: AsyncEngine, test_database_url: str
) -> None:
    llm = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200)))
    chatwoot = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200)))
    config = load_config(VALID | {"DATABASE_URL": test_database_url, "LLM_READS_IMAGES": "true"})
    config = replace(
        config, llm=replace(config.llm, transport=llm), chatwoot=replace(config.chatwoot, transport=chatwoot)
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        assert (llm.closed, chatwoot.closed) == (0, 0)
    # The Chatwoot calls and the image downloads have a client each.
    assert (llm.closed, chatwoot.closed) == (1, 2)


async def test_builds_the_audio_transcription_only_with_its_settings_and_closes_its_clients(
    engine: AsyncEngine, test_database_url: str
) -> None:
    stt = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200)))
    chatwoot = TrackedTransport(httpx.MockTransport(lambda _: httpx.Response(200)))
    transcribe = {"TRANSCRIBE_BASE_URL": "https://stt.example/v1", "TRANSCRIBE_API_KEY": "k", "TRANSCRIBE_MODEL": "m"}
    config = load_config(VALID | {"DATABASE_URL": test_database_url} | transcribe)
    assert config.transcription is not None
    config = replace(
        config,
        chatwoot=replace(config.chatwoot, transport=chatwoot),
        transcription=replace(config.transcription, transport=stt),
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        deps = app.state.geniai.deps
        assert deps.transcription is not None
        assert deps.media is None
        assert (stt.closed, chatwoot.closed) == (0, 0)
    # The Chatwoot calls and the audio downloads have a client each; image reading is off.
    assert (stt.closed, chatwoot.closed) == (1, 2)


async def test_leaves_audio_transcription_off_without_its_settings(engine: AsyncEngine, test_database_url: str) -> None:
    app = create_app(load_config(VALID | {"DATABASE_URL": test_database_url}))
    async with app.router.lifespan_context(app):
        assert app.state.geniai.deps.transcription is None
