from collections.abc import AsyncIterator

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from geniai.db.engine import asyncpg_connect_args, create_engine, to_async_url
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


@pytest.mark.parametrize(
    ("url", "expected_url", "expected_args"),
    [
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db", {"ssl": "require"}),
        (
            "postgresql://u:p@h/db?sslmode=verify-full&application_name=x",
            "postgresql+asyncpg://u:p@h/db?application_name=x",
            {"ssl": "verify-full"},
        ),
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db", {}),
    ],
)
def test_translates_sslmode_to_the_asyncpg_ssl_argument(
    url: str, expected_url: str, expected_args: dict[str, str]
) -> None:
    assert asyncpg_connect_args(url) == (expected_url, expected_args)


def test_rejects_an_unknown_sslmode() -> None:
    with pytest.raises(ValueError, match="sslmode"):
        asyncpg_connect_args("postgresql://u:p@h/db?sslmode=sometimes")


async def test_connects_with_sslmode_in_the_url(test_database_url: str) -> None:
    sep = "&" if "?" in test_database_url else "?"
    eng = create_engine(f"{test_database_url}{sep}sslmode=disable", poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            assert (await conn.execute(text("select 1"))).scalar_one() == 1
    finally:
        await eng.dispose()


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
