"""`python -m geniai.db.cli {create|migrate|seed}` and `load-faq <file.json>`, on DATABASE_URL."""

import asyncio
import os
import re
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text

from geniai.db.engine import create_engine
from geniai.db.faq_file import FaqFile, FaqFileError, load_faq, read_faq_file
from geniai.db.fixtures import has_data, seed_fictitious
from geniai.db.migrate import migrate

_DATABASE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def split_database(url: str) -> tuple[str, str]:
    """The database name in a PostgreSQL URL, and the same URL on the server's `postgres` database."""
    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    if not _DATABASE_NAME.match(name):
        raise ValueError(f"unexpected database name {name!r}: use lowercase letters, digits and _")
    return name, urlunsplit(parts._replace(path="/postgres"))


async def create_database(url: str) -> bool:
    """Creates the database of the URL when missing (the e2e database); needs the CREATEDB privilege.
    Returns whether it was created."""
    name, admin_url = split_database(url)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            query = text("SELECT 1 FROM pg_database WHERE datname = :name")
            if (await conn.execute(query, {"name": name})).first():
                return False
            # The name was checked against _DATABASE_NAME: CREATE DATABASE takes no bound parameter.
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
            return True
    finally:
        await engine.dispose()


async def _create(url: str) -> None:
    name, _ = split_database(url)
    print(f"Created database {name}." if await create_database(url) else f"Database {name} already exists.")


async def _migrate(url: str) -> None:
    engine = create_engine(url)
    try:
        applied = await migrate(engine)
    finally:
        await engine.dispose()
    print("No pending migrations." if not applied else f"Applied: {', '.join(applied)}")


async def _seed(url: str) -> None:
    """Loads FICTITIOUS data for local runs and demos. Real data is loaded by the team (spec §13)."""
    engine = create_engine(url)
    try:
        await migrate(engine)
        async with engine.begin() as conn:
            if await has_data(conn):
                print("Fictitious seed already present.")
                return
            await seed_fictitious(conn)
    finally:
        await engine.dispose()
    print("Fictitious seed loaded.")


async def _load_faq(url: str, faq: FaqFile) -> None:
    """Loads the FAQ file in one transaction (spec §13)."""
    engine = create_engine(url)
    try:
        await migrate(engine)
        async with engine.begin() as conn:
            summary = await load_faq(conn, faq)
    finally:
        await engine.dispose()
    print(summary.describe())


USAGE = "usage: python -m geniai.db.cli {create|migrate|seed} | load-faq <file.json>"


def main(argv: list[str]) -> int:
    commands: dict[str, Callable[[str], Coroutine[Any, Any, None]]] = {
        "create": _create,
        "migrate": _migrate,
        "seed": _seed,
    }
    if len(argv) == 1 and argv[0] in commands:
        command = commands[argv[0]]
    elif len(argv) == 2 and argv[0] == "load-faq":
        try:
            faq = read_faq_file(Path(argv[1]))
        except FaqFileError as err:
            print(err, file=sys.stderr)
            print("Invalid FAQ file; nothing was loaded.", file=sys.stderr)
            return 1

        async def command(url: str) -> None:
            await _load_faq(url, faq)
    else:
        print(USAGE, file=sys.stderr)
        return 2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    asyncio.run(command(url))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
