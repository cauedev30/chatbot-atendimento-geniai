"""Invented data only. Nothing here is a real unit, person or phone number.
Used by `python -m geniai.db.cli seed`, by the tests and by the evaluation set.
"""

from dataclasses import dataclass
from typing import Any, Final, TypedDict

from sqlalchemy import Table, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.db.schema import attendant, category, faq_item, team_member, unit


class FictitiousAttendant(TypedDict):
    name: str
    phone: str
    unit: str
    active: bool


class FictitiousCategory(TypedDict):
    system: str
    name: str


class FictitiousFaq(TypedDict):
    category: str
    title: str
    applies_when: str
    answer_text: str


class Fictitious(TypedDict):
    units: dict[str, str]
    attendants: dict[str, FictitiousAttendant]
    categories: dict[str, FictitiousCategory]
    faq: dict[str, FictitiousFaq]
    team: dict[str, str]


FICTITIOUS: Final[Fictitious] = {
    "units": {
        "centro": "Unidade Exemplo Centro",
        "norte": "Unidade Exemplo Norte",
    },
    "attendants": {
        "ana": {"name": "Ana Exemplo", "phone": "+5511900000001", "unit": "centro", "active": True},
        "bruno": {"name": "Bruno Exemplo", "phone": "+5511900000002", "unit": "centro", "active": True},
        "carla": {"name": "Carla Exemplo", "phone": "+5511900000003", "unit": "norte", "active": True},
        "inactive": {"name": "Davi Exemplo", "phone": "+5511900000004", "unit": "norte", "active": False},
    },
    "categories": {
        "login": {"system": "Painel", "name": "Não consegue entrar"},
        "report": {"system": "Painel", "name": "Relatório não carrega"},
        "schedule": {"system": "Agenda", "name": "Horário não aparece"},
        "whatsappDisconnected": {"system": "WhatsApp", "name": "Número desconectado"},
        "whatsappMessages": {"system": "WhatsApp", "name": "Mensagens não chegam"},
    },
    "faq": {
        "password": {
            "category": "login",
            "title": "Redefinir senha do painel",
            "applies_when": "A pessoa não consegue entrar no painel, esqueceu a senha ou a senha não é aceita.",
            "answer_text": (
                "1. Abra a tela de login do painel.\n"
                '2. Toque em "Esqueci minha senha".\n'
                "3. Abra o link que chegou no seu e-mail e crie uma senha nova."
            ),
        },
        "report": {
            "category": "report",
            "title": "Relatório em branco",
            "applies_when": "Um relatório do painel abre em branco ou fica carregando sem terminar.",
            "answer_text": (
                "1. Confira se o período escolhido tem movimento.\n"
                "2. Atualize a página com Ctrl+F5.\n"
                "3. Se continuar em branco, saia do painel e entre de novo."
            ),
        },
        "reconnect": {
            "category": "whatsappDisconnected",
            "title": "Reconectar o WhatsApp da unidade",
            "applies_when": "O número de WhatsApp da unidade aparece como desconectado no painel.",
            "answer_text": (
                "1. No painel, abra Configurações > WhatsApp.\n"
                '2. Toque em "Reconectar".\n'
                "3. No celular da unidade, leia o QR Code que aparecer."
            ),
        },
    },
    "team": {
        "first": "Pessoa Suporte 1",
        "second": "Pessoa Suporte 2",
    },
}


@dataclass(frozen=True)
class SeededAttendant:
    id: int
    phone: str
    unit_id: int


@dataclass(frozen=True)
class SeedResult:
    units: dict[str, int]
    attendants: dict[str, SeededAttendant]
    categories: dict[str, int]
    """The FICTITIOUS category keys plus the system categories "other" and "unidentified"."""
    faq: dict[str, int]
    team: dict[str, int]


async def _get_or_insert(conn: AsyncConnection, table: Table, match: dict[str, Any], extra: dict[str, Any]) -> int:
    """Returns the id of the row matching `match`, inserting it (with `extra`) when missing."""
    query = select(table.c.id).where(*(table.c[k] == v for k, v in match.items())).order_by(table.c.id).limit(1)
    found = (await conn.execute(query)).scalar_one_or_none()
    if found is not None:
        return int(found)
    inserted = await conn.execute(insert(table).values(**match, **extra).returning(table.c.id))
    return int(inserted.scalar_one())


async def seed_fictitious(conn: AsyncConnection) -> SeedResult:
    """Loads FICTITIOUS. Idempotent: rows already present are reused, so running it twice does not duplicate."""
    units = {key: await _get_or_insert(conn, unit, {"name": name}, {}) for key, name in FICTITIOUS["units"].items()}
    attendants: dict[str, SeededAttendant] = {}
    for key, a in FICTITIOUS["attendants"].items():
        unit_id = units[a["unit"]]
        row_id = await _get_or_insert(
            conn, attendant, {"phone_e164": a["phone"]}, {"name": a["name"], "unit_id": unit_id, "active": a["active"]}
        )
        attendants[key] = SeededAttendant(id=row_id, phone=a["phone"], unit_id=unit_id)
    categories: dict[str, int] = {}
    system_rows = await conn.execute(select(category.c.id, category.c.key).where(category.c.key.is_not(None)))
    for row in system_rows:
        if row.key in ("other", "unidentified"):
            categories[row.key] = row.id
    for key, c in FICTITIOUS["categories"].items():
        categories[key] = await _get_or_insert(
            conn, category, {"system": c["system"], "name": c["name"], "key": None}, {}
        )
    faq: dict[str, int] = {}
    for key, f in FICTITIOUS["faq"].items():
        faq[key] = await _get_or_insert(
            conn,
            faq_item,
            {"category_id": categories[f["category"]], "title": f["title"]},
            {"applies_when": f["applies_when"], "answer_text": f["answer_text"]},
        )
    team = {
        key: await _get_or_insert(conn, team_member, {"name": name}, {}) for key, name in FICTITIOUS["team"].items()
    }
    return SeedResult(units=units, attendants=attendants, categories=categories, faq=faq, team=team)


async def has_data(conn: AsyncConnection) -> bool:
    """True when the database already has active units."""
    query = select(unit.c.id).where(unit.c.active.is_(True)).limit(1)
    return (await conn.execute(query)).first() is not None
