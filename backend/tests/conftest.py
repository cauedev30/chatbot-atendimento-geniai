import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.pool import NullPool

from geniai.app.ports import Deps
from geniai.db.engine import create_engine
from geniai.db.fixtures import SeedResult, seed_fictitious
from geniai.db.migrate import migrate
from geniai.domain.rules import DEFAULT_RULES
from tests.support.fakes import FakeChatwoot, RecordingLogger, ScriptedLlm

RESET_SQL = (
    "TRUNCATE ticket_move, triage_message, ticket, faq_item, attendant, unit, team_member RESTART IDENTITY CASCADE"
)


def _test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set: point it to an empty, dedicated PostgreSQL database.", 2)
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _test_url()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """Migrates the test database once, on its own event loop, before any test."""

    async def run() -> None:
        engine = create_engine(_test_url(), poolclass=NullPool)
        try:
            await migrate(engine)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A fresh engine per test, on an emptied database. Its pool is disposed when the test ends, so no
    connection crosses event loops; pooling keeps the ~100 ms connection setup out of every transaction."""
    eng = create_engine(_test_url())
    async with eng.begin() as conn:
        await conn.execute(text(RESET_SQL))
        await conn.execute(text("DELETE FROM category WHERE key IS NULL"))
    yield eng
    await eng.dispose()


START = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)  # 12:00 in São Paulo


@dataclass
class Harness:
    """Real test database + fictitious seed + fakes + a clock the test controls."""

    engine: AsyncEngine
    seed: SeedResult
    now: datetime = START
    chatwoot: FakeChatwoot = field(default_factory=FakeChatwoot)
    llm: ScriptedLlm = field(default_factory=ScriptedLlm)
    logger: RecordingLogger = field(default_factory=RecordingLogger)
    deps: Deps = field(init=False)

    def __post_init__(self) -> None:
        self.deps = Deps(
            engine=self.engine,
            llm=self.llm,
            chatwoot=self.chatwoot,
            rules=DEFAULT_RULES,
            now=lambda: self.now,
            log=self.logger,
        )

    def advance(self, ms: int) -> None:
        self.now = self.now + timedelta(milliseconds=ms)

    def with_rules(self, **overrides: Any) -> None:
        self.deps.rules = replace(DEFAULT_RULES, **overrides)

    def begin(self) -> AbstractAsyncContextManager[AsyncConnection]:
        """One connection in one transaction, like a use case's unit of work."""
        return self.engine.begin()


@pytest.fixture
async def h(engine: AsyncEngine) -> Harness:
    async with engine.begin() as conn:
        seed = await seed_fictitious(conn)
    return Harness(engine=engine, seed=seed)
