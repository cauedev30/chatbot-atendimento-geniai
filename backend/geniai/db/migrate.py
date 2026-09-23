import re
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from geniai.db.schema import schema_migration

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_STATEMENT_END = re.compile(r";[ \t]*(?:\n|\Z)")


def split_statements(text: str) -> list[str]:
    """asyncpg prepares one statement per call, so migration files are split on ";" at end of line.
    Keep migration SQL simple: no functions or DO blocks with inner semicolons at line ends.
    """
    lines = [line for line in re.split(r"\r?\n", text) if not line.strip().startswith("--")]
    statements = (statement.strip() for statement in _STATEMENT_END.split("\n".join(lines)))
    return [statement for statement in statements if statement]


async def migrate(engine: AsyncEngine) -> list[str]:
    """Applies geniai/db/migrations/*.sql in name order, each file in one transaction. Returns the applied names."""
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migration "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = set((await conn.execute(select(schema_migration.c.name))).scalars())
    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        statements = split_statements(path.read_text(encoding="utf-8"))
        async with engine.begin() as conn:
            for statement in statements:
                await conn.exec_driver_sql(statement)
            await conn.execute(insert(schema_migration).values(name=path.name))
        applied.append(path.name)
    return applied
