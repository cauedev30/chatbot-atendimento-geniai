from dataclasses import dataclass
from typing import Final

from geniai.db.fixtures import FICTITIOUS
from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.texts import TEXT, category_label
from geniai.domain.types import TriageState
from geniai.llm.prompt import PromptCategory, PromptFaqItem, PromptMessage, TurnContext


@dataclass(frozen=True)
class EvalCategory:
    id: int
    system: str
    name: str
    label: str


@dataclass(frozen=True)
class EvalCatalog:
    categories: list[EvalCategory]
    faq_items: list[PromptFaqItem]


def build_catalog() -> EvalCatalog:
    """The fictitious catalog with stable ids, no database needed."""
    category_keys = list(FICTITIOUS["categories"])
    categories = [
        EvalCategory(id=i + 1, system=c["system"], name=c["name"], label=category_label(c["system"], c["name"]))
        for i, c in enumerate(FICTITIOUS["categories"].values())
    ]
    categories.append(EvalCategory(id=100, system="Geral", name="Outros", label=category_label("Geral", "Outros")))
    faq_items = [
        PromptFaqItem(
            id=i + 1,
            category_id=category_keys.index(f["category"]) + 1,
            title=f["title"],
            applies_when=f["applies_when"],
        )
        for i, f in enumerate(FICTITIOUS["faq"].values())
    ]
    return EvalCatalog(categories=categories, faq_items=faq_items)


@dataclass(frozen=True)
class Expected:
    human_requested: bool
    category: str
    faq: str | None


@dataclass(frozen=True)
class EvalCase:
    id: str
    customer: list[str]
    expected: Expected


LOGIN = "Painel / Não consegue entrar"
REPORT = "Painel / Relatório não carrega"
SCHEDULE = "Agenda / Horário não aparece"
WA_DOWN = "WhatsApp / Número desconectado"
WA_MESSAGES = "WhatsApp / Mensagens não chegam"
OTHER = "Geral / Outros"
PASSWORD = FICTITIOUS["faq"]["password"]["title"]
BLANK_REPORT = FICTITIOUS["faq"]["report"]["title"]
RECONNECT = FICTITIOUS["faq"]["reconnect"]["title"]


def _case(id: str, text: str, human_requested: bool, category: str, faq: str | None) -> EvalCase:
    return EvalCase(id=id, customer=[text], expected=Expected(human_requested, category, faq))


CASES: Final[list[EvalCase]] = [
    _case("01", "sou eu sim. não consigo entrar no painel, diz que a senha está errada", False, LOGIN, PASSWORD),
    _case("02", "isso. esqueci minha senha do painel", False, LOGIN, PASSWORD),
    _case("03", "sim. o relatório de vendas abre em branco", False, REPORT, BLANK_REPORT),
    _case("04", "sou eu. o relatório fica carregando e não termina nunca", False, REPORT, BLANK_REPORT),
    _case("05", "sim, o whatsapp da unidade aparece desconectado no painel", False, WA_DOWN, RECONNECT),
    _case("06", "isso mesmo. nosso número caiu, tá desconectado", False, WA_DOWN, RECONNECT),
    _case("07", "sim. os clientes dizem que mandam mensagem e não chega pra gente", False, WA_MESSAGES, None),
    _case("08", "sou eu. o horário das 15h sumiu da agenda", False, SCHEDULE, None),
    _case("09", "sim. a agenda de amanhã não mostra os horários", False, SCHEDULE, None),
    _case("10", "sim. queria saber como emitir nota fiscal", False, OTHER, None),
    _case("11", "sou eu. quero falar com um atendente", True, OTHER, None),
    _case("12", "sim, mas prefiro falar com uma pessoa de verdade", True, OTHER, None),
    _case("13", "me passa pra alguém da equipe por favor", True, OTHER, None),
    _case("14", "não quero falar com robô", True, OTHER, None),
    _case("15", "tem algum humano aí?", True, OTHER, None),
    _case("16", "sou eu. o painel não entra de jeito nenhum, alguém do suporte pode me ligar?", True, LOGIN, None),
    _case("17", "sim. o relatório não carrega. pode chamar o suporte pra mim?", True, REPORT, None),
    _case("18", "quero conversar com o pessoal do suporte, não com bot", True, OTHER, None),
    _case("19", "chama a equipe, é urgente, o whatsapp caiu", True, WA_DOWN, None),
    _case("20", "dá pra alguém me atender? a agenda travou", True, SCHEDULE, None),
    _case("21", "sim, sou eu. não lembro a senha do painel", False, LOGIN, PASSWORD),
    _case("22", "sim. as mensagens do whatsapp demoram horas pra chegar", False, WA_MESSAGES, None),
    _case("23", "sim. troquei o celular da unidade e o whatsapp desconectou", False, WA_DOWN, RECONNECT),
    _case("24", "sou eu. a senha do painel não é aceita desde ontem", False, LOGIN, PASSWORD),
    _case("25", "sim. o relatório mensal aparece vazio mesmo tendo vendas", False, REPORT, BLANK_REPORT),
    _case("26", "sim. quero cancelar o contrato", False, OTHER, None),
    _case("27", "sim. um cliente marcou e o horário não aparece na agenda", False, SCHEDULE, None),
    _case("28", "sou eu. como faço para pagar o boleto?", False, OTHER, None),
    _case("29", "sim, a pessoa do caixa não consegue entrar no painel", False, LOGIN, PASSWORD),
    _case("30", "isso. o whatsapp não recebe mensagens desde cedo", False, WA_MESSAGES, None),
]
"""30 invented conversations. 10 ask for a human; case 29 is a keyword trap ("a pessoa do caixa")."""

_ATTENDANT = FICTITIOUS["attendants"]["ana"]
_UNIT = FICTITIOUS["units"]["centro"]


def context_for(c: EvalCase, catalog: EvalCatalog) -> TurnContext:
    return TurnContext(
        attendant_name=_ATTENDANT["name"],
        unit_name=_UNIT,
        categories=[PromptCategory(id=x.id, system=x.system, name=x.name) for x in catalog.categories],
        faq_items=catalog.faq_items,
        messages=[
            PromptMessage(author="bot", text=TEXT.greeting(_ATTENDANT["name"], _UNIT)),
            *(PromptMessage(author="customer", text=text) for text in c.customer),
        ],
        state=TriageState(faq_attempted=False, clarifications_asked=0, unclear_feedback_reasks=0, media_prompts=0),
        max_clarifications=DEFAULT_RULES.max_clarifications,
    )
