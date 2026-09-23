"""`python -m geniai.db.cli migrate` and `python -m geniai.db.cli seed`, on DATABASE_URL."""

import asyncio
import os
import sys

from geniai.db.engine import create_engine
from geniai.db.fixtures import has_data, seed_fictitious
from geniai.db.migrate import migrate


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


def main(argv: list[str]) -> int:
    commands = {"migrate": _migrate, "seed": _seed}
    if len(argv) != 1 or argv[0] not in commands:
        print("usage: python -m geniai.db.cli {migrate|seed}", file=sys.stderr)
        return 2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    asyncio.run(commands[argv[0]](url))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
