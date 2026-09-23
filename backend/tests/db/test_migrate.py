from collections.abc import AsyncIterator

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from geniai.db.engine import create_engine, to_async_url
from geniai.db.migrate import migrate, split_statements
from geniai.db.schema import category, ticket, unit

SCRATCH_SCHEMA = "migrate_test"


def test_splits_on_semicolons_at_end_of_line_and_drops_comment_lines() -> None:
    sql = "-- header\nCREATE TABLE a (x int);\r\nCREATE TABLE b (\n  y int\n);\n"
    assert split_statements(sql) == ["CREATE TABLE a (x int)", "CREATE TABLE b (\n  y int\n)"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u@h/db", "postgresql+asyncpg://u@h/db"),
    ],
)
def test_to_async_url_selects_the_asyncpg_driver(url: str, expected: str) -> None:
    assert to_async_url(url) == expected


@pytest.fixture
async def scratch_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose search_path is an empty schema, so migrate() starts from nothing."""
    admin = create_engine(test_database_url, poolclass=NullPool)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCRATCH_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCRATCH_SCHEMA}"))
    eng = create_engine(
        test_database_url, poolclass=NullPool, connect_args={"server_settings": {"search_path": SCRATCH_SCHEMA}}
    )
    yield eng
    await eng.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCRATCH_SCHEMA} CASCADE"))
    await admin.dispose()


async def test_applies_pending_migrations_once_and_seeds_system_categories(scratch_engine: AsyncEngine) -> None:
    assert await migrate(scratch_engine) == ["0001_init.sql"]
    assert await migrate(scratch_engine) == []
    async with scratch_engine.connect() as conn:
        keys = sorted((await conn.execute(select(category.c.key))).scalars())
    assert keys == ["other", "unidentified"]


async def test_allows_only_one_open_ticket_per_conversation(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        unit_id = (await conn.execute(insert(unit).values(name="Unidade Exemplo").returning(unit.c.id))).scalar_one()
        await conn.execute(insert(ticket).values(column="in_triage", chatwoot_conversation_id=7, unit_id=unit_id))
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(insert(ticket).values(column="awaiting_human", chatwoot_conversation_id=7))
    async with engine.begin() as conn:
        await conn.execute(
            update(ticket).where(ticket.c.chatwoot_conversation_id == 7).values(column="resolved_by_bot")
        )
        await conn.execute(insert(ticket).values(column="in_triage", chatwoot_conversation_id=7))
