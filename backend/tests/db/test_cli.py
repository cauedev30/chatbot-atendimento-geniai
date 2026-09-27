from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import text

from geniai.db.cli import create_database, split_database
from geniai.db.engine import create_engine

SCRATCH_DATABASE = "geniai_cli_test_scratch"


def test_splits_the_database_from_the_url_and_points_to_the_maintenance_database() -> None:
    name, admin = split_database("postgresql://u:p@localhost:5432/geniai_e2e?sslmode=disable")
    assert (name, admin) == ("geniai_e2e", "postgresql://u:p@localhost:5432/postgres?sslmode=disable")
    for bad in ("postgresql://u:p@localhost/", 'postgresql://u:p@localhost/x"; DROP', "postgresql://h/Geniai"):
        with pytest.raises(ValueError):
            split_database(bad)


async def test_creates_a_missing_database_once(test_database_url: str) -> None:
    _, admin = split_database(test_database_url)
    url = urlunsplit(urlsplit(test_database_url)._replace(path=f"/{SCRATCH_DATABASE}"))
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}"'))
        assert await create_database(url) is True
        assert await create_database(url) is False
    finally:
        async with engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}"'))
        await engine.dispose()
