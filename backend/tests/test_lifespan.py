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
