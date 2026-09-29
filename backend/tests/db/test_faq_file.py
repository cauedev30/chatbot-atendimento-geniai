import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from geniai.db.cli import main
from geniai.db.faq_file import FAQ_FILE, FaqFile, FaqFileError, LoadSummary, load_faq, parse_faq_file, read_faq_file
from geniai.db.schema import category, faq_item
from tests.conftest import Harness

VALID: dict[str, Any] = {
    "categories": [
        {"key": "panel", "system": "Painel", "name": "Acesso"},
        {"key": "agenda", "system": "Agenda", "name": "Horários"},
        {"key": "other", "system": "Geral", "name": "Outros assuntos"},
    ],
    "items": [
        {
            "category": "panel",
            "title": "Senha do painel",
            "applies_when": "Não consegue entrar no painel.",
            "answer_text": "Faça assim:\n-> Abra o login.\n\nDepois me conta.",
            "knowledge_base": "- O link vale por 1 hora.",
        },
        {
            "category": "agenda",
            "title": "Horário sumiu",
            "applies_when": "Um horário não aparece na agenda.",
            "answer_text": "Atualize a agenda.",
        },
    ],
}


def with_changes(**changes: Any) -> dict[str, Any]:
    return json.loads(json.dumps(VALID)) | changes


def errors_of(raw: object) -> str:
    with pytest.raises(FaqFileError) as info:
        parse_faq_file(raw)
    return str(info.value)


def test_reads_the_documented_format_keeping_the_texts_as_written() -> None:
    faq = parse_faq_file(VALID)
    assert [c.key for c in faq.categories] == ["panel", "agenda", "other"]
    assert faq.items[0].answer_text == "Faça assim:\n-> Abra o login.\n\nDepois me conta."
    assert faq.items[1].knowledge_base == ""


def test_rejects_an_empty_required_field() -> None:
    items = with_changes()["items"]
    items[0]["answer_text"] = "  "
    assert "answer_text" in errors_of(with_changes(items=items))


def test_rejects_a_category_without_a_system() -> None:
    missing = with_changes()
    del missing["categories"][0]["system"]
    assert "categories.0.system" in errors_of(missing)
    blank = with_changes()
    blank["categories"][1]["system"] = " "
    assert "categories.1.system" in errors_of(blank)


def test_rejects_an_item_of_a_category_not_in_the_file() -> None:
    items = with_changes()["items"]
    items[1]["category"] = "finance"
    assert '"finance"' in errors_of(with_changes(items=items))


def test_rejects_a_repeated_title_a_repeated_key_and_the_unidentified_category() -> None:
    data = with_changes()
    data["items"][1]["title"] = "Senha do painel"
    data["categories"].append({"key": "panel", "system": "Painel", "name": "De novo"})
    data["categories"].append({"key": "unidentified", "system": "Geral", "name": "Sem cadastro"})
    message = errors_of(data)
    assert '"Senha do painel"' in message
    assert '"panel"' in message
    assert '"unidentified"' in message


def test_rejects_unknown_fields_and_non_text_values() -> None:
    assert "extra" in errors_of(with_changes(extra=True))
    items = with_changes()["items"]
    items[0]["knowledge_base"] = None
    assert "knowledge_base" in errors_of(with_changes(items=items))


def test_reports_a_file_that_is_missing_or_not_json(tmp_path: Path) -> None:
    with pytest.raises(FaqFileError):
        read_faq_file(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(FaqFileError):
        read_faq_file(bad)


def test_the_command_refuses_an_invalid_file_before_touching_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "faq.json"
    bad.write_text(json.dumps(with_changes(items=[])) + "x", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@invalid.invalid:1/none")
    assert main(["load-faq", str(bad)]) == 1
    assert "nothing was loaded" in capsys.readouterr().err
    assert main(["load-faq"]) == 2


async def test_a_file_with_a_category_without_a_system_loads_nothing(
    h: Harness, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = await categories_by_key(h)
    data = with_changes()
    del data["categories"][0]["system"]
    bad = tmp_path / "faq.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    assert main(["load-faq", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "categories.0.system" in err
    assert "nothing was loaded" in err
    assert await categories_by_key(h) == before


async def load(h: Harness, faq: FaqFile) -> LoadSummary:
    async with h.begin() as conn:
        return await load_faq(conn, faq)


async def active_items(h: Harness) -> dict[str, tuple[str, str]]:
    async with h.begin() as conn:
        query = (
            select(faq_item.c.title, category.c.key, faq_item.c.knowledge_base)
            .join(category, faq_item.c.category_id == category.c.id)
            .where(faq_item.c.active.is_(True))
        )
        return {r.title: (r.key, r.knowledge_base) for r in await conn.execute(query)}


async def categories_by_key(h: Harness) -> dict[str | None, list[tuple[str, str, bool]]]:
    async with h.begin() as conn:
        rows = await conn.execute(select(category.c.key, category.c.system, category.c.name, category.c.active))
        found: dict[str | None, list[tuple[str, str, bool]]] = {}
        for r in rows:
            found.setdefault(r.key, []).append((r.system, r.name, r.active))
        return found


async def test_loads_the_file_and_retires_what_it_does_not_list(h: Harness) -> None:
    summary = await load(h, parse_faq_file(VALID))
    assert summary == LoadSummary(
        categories_created=2,
        categories_updated=1,
        categories_unchanged=0,
        categories_deactivated=5,
        items_created=2,
        items_updated=0,
        items_unchanged=0,
        items_deactivated=3,
    )
    assert await active_items(h) == {
        "Senha do painel": ("panel", "- O link vale por 1 hora."),
        "Horário sumiu": ("agenda", ""),
    }
    found = await categories_by_key(h)
    assert found["panel"] == [("Painel", "Acesso", True)]
    assert found["agenda"] == [("Agenda", "Horários", True)]
    assert found["other"] == [("Geral", "Outros assuntos", True)]
    assert found["unidentified"] == [("Geral", "Não identificado", True)]
    # The categories the file does not list stay, inactive: tickets and indicators still point to them.
    assert [active for *_, active in found[None]] == [False] * 5


async def test_loading_the_same_file_again_changes_nothing(h: Harness) -> None:
    faq = parse_faq_file(VALID)
    await load(h, faq)
    before = (await active_items(h), await categories_by_key(h))
    summary = await load(h, faq)
    assert (summary.items_created, summary.items_updated, summary.items_unchanged, summary.items_deactivated) == (
        0,
        0,
        2,
        0,
    )
    assert (summary.categories_created, summary.categories_updated, summary.categories_deactivated) == (0, 0, 0)
    assert (await active_items(h), await categories_by_key(h)) == before


async def test_updates_edited_items_and_brings_back_a_listed_item_or_category(h: Harness) -> None:
    await load(h, parse_faq_file(VALID))
    only_panel = with_changes(categories=VALID["categories"][:1], items=VALID["items"][:1])
    summary = await load(h, parse_faq_file(only_panel))
    assert (summary.items_deactivated, summary.categories_deactivated) == (1, 1)
    assert list(await active_items(h)) == ["Senha do painel"]

    edited = with_changes()
    edited["items"][0]["knowledge_base"] = "- O link vale por 2 horas."
    summary = await load(h, parse_faq_file(edited))
    assert (summary.items_created, summary.items_updated, summary.items_unchanged) == (0, 2, 0)
    assert summary.categories_updated == 1
    assert (await active_items(h))["Senha do painel"] == ("panel", "- O link vale por 2 horas.")
    assert (await categories_by_key(h))["agenda"] == [("Agenda", "Horários", True)]


async def test_a_new_system_for_a_category_is_an_update(h: Harness) -> None:
    await load(h, parse_faq_file(VALID))
    moved = with_changes()
    moved["categories"][0]["system"] = "Chatwoot"
    moved["categories"][2]["system"] = "Suporte"
    summary = await load(h, parse_faq_file(moved))
    assert (summary.categories_created, summary.categories_updated, summary.categories_unchanged) == (0, 2, 1)
    assert (summary.items_updated, summary.items_unchanged) == (0, 2)
    found = await categories_by_key(h)
    assert found["panel"] == [("Chatwoot", "Acesso", True)]
    assert found["other"] == [("Suporte", "Outros assuntos", True)]
    assert found["unidentified"] == [("Geral", "Não identificado", True)]
    summary = await load(h, parse_faq_file(moved))
    assert (summary.categories_updated, summary.categories_unchanged) == (0, 3)


def test_the_faq_file_in_the_repository_is_valid() -> None:
    faq = read_faq_file(FAQ_FILE)
    assert [c.key for c in faq.categories] == [
        "dispatch_failure",
        "templates",
        "number_quality",
        "new_number",
        "access",
        "chat_usage",
        "dispatcher_usage",
        "billing",
        "other",
    ]
    assert {c.key: c.system for c in faq.categories} == {
        "dispatch_failure": "Disparador",
        "templates": "Disparador",
        "number_quality": "Disparador",
        "new_number": "Disparador",
        "access": "Disparador",
        "chat_usage": "Chatwoot",
        "dispatcher_usage": "Disparador",
        "billing": "Geral",
        "other": "Geral",
    }
    assert len(faq.items) == 17
    assert {c.key for c in faq.categories} >= {i.category for i in faq.items}
    for item in faq.items:
        assert "**" not in item.knowledge_base, item.title
        assert all(line.startswith("- ") for line in item.knowledge_base.splitlines()), item.title
    empty = [i.title for i in faq.items if i.knowledge_base == ""]
    assert empty == ["Áudio sem som no Chat", "Chat trava, cai ou não atualiza"]
