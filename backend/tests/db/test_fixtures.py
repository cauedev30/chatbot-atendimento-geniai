from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from geniai.db.fixtures import FICTITIOUS, has_data, seed_fictitious
from geniai.db.schema import attendant, category, faq_item, team_member, unit


async def _count(engine: AsyncEngine, table: object) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(table))).scalar_one()  # type: ignore[arg-type]


async def test_inserts_the_fictitious_catalog_and_returns_its_ids(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        seed = await seed_fictitious(conn)
    assert seed.attendants["ana"].phone == FICTITIOUS["attendants"]["ana"]["phone"]
    assert seed.categories["other"] > 0
    assert seed.categories["unidentified"] > 0
    assert await _count(engine, attendant) == len(FICTITIOUS["attendants"])
    assert await _count(engine, faq_item) == len(FICTITIOUS["faq"])
    assert await _count(engine, team_member) == len(FICTITIOUS["team"])


async def test_keeps_the_inactive_attendant_inactive(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        seed = await seed_fictitious(conn)
        active = (
            await conn.execute(select(attendant.c.active).where(attendant.c.id == seed.attendants["inactive"].id))
        ).scalar_one()
    assert active is False


async def test_is_idempotent_running_twice_returns_the_same_ids_without_duplicates(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        assert await has_data(conn) is False
        first = await seed_fictitious(conn)
    async with engine.begin() as conn:
        assert await has_data(conn) is True
        second = await seed_fictitious(conn)
    assert first == second
    assert await _count(engine, unit) == len(FICTITIOUS["units"])
    assert await _count(engine, category) == len(FICTITIOUS["categories"]) + 2
    assert await _count(engine, faq_item) == len(FICTITIOUS["faq"])
