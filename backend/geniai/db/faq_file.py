"""The FAQ file and its loader: `python -m geniai.db.cli load-faq <file.json>`.

The team edits the FAQ in `backend/faq/faq.json` and loads it with the command. Each category has its
`system` and `name`, shown together as "system / name". Loading is one transaction and can be repeated:
categories are matched by `key` and entries by (category, title); what the file no longer lists is
deactivated, never deleted, since tickets and indicators point to it.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictStr, ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.db.schema import category, faq_item

FAQ_FILE: Final = Path(__file__).resolve().parents[2] / "faq" / "faq.json"
"""The FAQ the team maintains, in the repository."""

SYSTEM_KEYS: Final = frozenset({"other", "unidentified"})
"""Categories created by the migrations; the file may rename "other" and never touches "unidentified"."""


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty")
    return value


Text = Annotated[StrictStr, AfterValidator(_not_blank)]


class FaqFileCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Text
    system: Text
    name: Text


class FaqFileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Text
    title: Text
    applies_when: Text
    answer_text: Text
    knowledge_base: StrictStr = ""


class FaqFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[FaqFileCategory]
    items: list[FaqFileItem]


class FaqFileError(ValueError):
    """The file is not a valid FAQ file; the message lists every problem found."""


def _repeated(values: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for v in values:
        (repeated if v in seen else seen).add(v)
    return sorted(repeated)


def parse_faq_file(raw: object) -> FaqFile:
    """Validates the whole file before anything is written. Raises FaqFileError."""
    try:
        faq = FaqFile.model_validate(raw)
    except ValidationError as err:
        problems = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()]
        raise FaqFileError("\n".join(problems)) from err
    problems = []
    keys = [c.key for c in faq.categories]
    problems += [f'category key "{k}" is repeated' for k in _repeated(keys)]
    if "unidentified" in keys:
        problems.append('category key "unidentified" is reserved for unknown numbers')
    for i, item in enumerate(faq.items):
        if item.category not in keys:
            problems.append(f'items.{i}: category "{item.category}" is not in the file\'s categories')
    problems += [f'item title "{t}" is repeated' for t in _repeated([i.title for i in faq.items])]
    if problems:
        raise FaqFileError("\n".join(problems))
    return faq


def read_faq_file(path: Path) -> FaqFile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise FaqFileError(f"cannot read {path}: {err}") from err
    return parse_faq_file(raw)


@dataclass(frozen=True)
class LoadSummary:
    categories_created: int
    categories_updated: int
    categories_unchanged: int
    categories_deactivated: int
    items_created: int
    items_updated: int
    items_unchanged: int
    items_deactivated: int

    def describe(self) -> str:
        return (
            f"FAQ loaded. Items: {self.items_created} created, {self.items_updated} updated, "
            f"{self.items_unchanged} unchanged, {self.items_deactivated} deactivated. "
            f"Categories: {self.categories_created} created, {self.categories_updated} updated, "
            f"{self.categories_unchanged} unchanged, {self.categories_deactivated} deactivated."
        )


_Counts = tuple[int, int, int, int]
"""Created, updated, unchanged, deactivated."""


async def _load_categories(conn: AsyncConnection, faq: FaqFile) -> tuple[dict[str, int], _Counts]:
    """Returns the category ids by key and the counts."""
    rows = {r.key: r for r in await conn.execute(select(category).where(category.c.key.is_not(None)))}
    ids: dict[str, int] = {}
    created = updated = unchanged = 0
    for c in faq.categories:
        row = rows.get(c.key)
        if row is None:
            query = insert(category).values(key=c.key, system=c.system, name=c.name).returning(category.c.id)
            ids[c.key] = int((await conn.execute(query)).scalar_one())
            created += 1
            continue
        ids[c.key] = row.id
        if (row.system, row.name, row.active) == (c.system, c.name, True):
            unchanged += 1
            continue
        values = {"system": c.system, "name": c.name, "active": True}
        await conn.execute(update(category).where(category.c.id == row.id).values(**values))
        updated += 1
    retired = await conn.execute(
        update(category)
        .where(
            category.c.active.is_(True),
            category.c.key.is_(None) | category.c.key.not_in([*SYSTEM_KEYS, *ids]),
        )
        .values(active=False)
        .returning(category.c.id)
    )
    return ids, (created, updated, unchanged, len(retired.all()))


async def load_faq(conn: AsyncConnection, faq: FaqFile) -> LoadSummary:
    """Loads a validated FAQ file on the caller's transaction. Idempotent."""
    category_ids, (c_created, c_updated, c_unchanged, c_deactivated) = await _load_categories(conn, faq)
    existing: dict[tuple[int, str], int] = {}
    for r in await conn.execute(select(faq_item).order_by(faq_item.c.id.desc())):
        existing[(r.category_id, r.title)] = r.id  # the oldest row wins when a pair repeats
    current = {r.id: r for r in await conn.execute(select(faq_item))}
    kept: list[int] = []
    created = updated = unchanged = 0
    for item in faq.items:
        category_id = category_ids[item.category]
        values = {
            "applies_when": item.applies_when,
            "answer_text": item.answer_text,
            "knowledge_base": item.knowledge_base,
            "active": True,
        }
        found = existing.get((category_id, item.title))
        if found is None:
            query = insert(faq_item).values(category_id=category_id, title=item.title, **values)
            kept.append(int((await conn.execute(query.returning(faq_item.c.id))).scalar_one()))
            created += 1
            continue
        kept.append(found)
        row = current[found]
        if all(getattr(row, k) == v for k, v in values.items()):
            unchanged += 1
            continue
        await conn.execute(update(faq_item).where(faq_item.c.id == found).values(**values))
        updated += 1
    retired = await conn.execute(
        update(faq_item)
        .where(faq_item.c.active.is_(True), faq_item.c.id.not_in(kept))
        .values(active=False)
        .returning(faq_item.c.id)
    )
    return LoadSummary(
        categories_created=c_created,
        categories_updated=c_updated,
        categories_unchanged=c_unchanged,
        categories_deactivated=c_deactivated,
        items_created=created,
        items_updated=updated,
        items_unchanged=unchanged,
        items_deactivated=len(retired.all()),
    )
