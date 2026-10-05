from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from geniai.app.ports import ImageData
from geniai.db.fixtures import FICTITIOUS
from geniai.domain import attachments as label
from geniai.domain.rules import DEFAULT_RULES
from geniai.domain.texts import TEXT, category_label
from geniai.domain.types import FaqFeedback, TriageState
from geniai.llm.prompt import PromptCategory, PromptFaqItem, PromptMessage, PromptSentFaq, TurnContext


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
    clarifies: bool = False
    """The bot asks a question: no FAQ entry and needs_clarification true (owner, 2026-10-04: only while the
    customer has not yet said what the problem is)."""


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


def _case(
    id: str, text: str, human_requested: bool, category: str, faq: str | None, clarifies: bool = False
) -> EvalCase:
    return EvalCase(id=id, customer=[text], expected=Expected(human_requested, category, faq, clarifies))


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
    _case("31", "sim. preciso do relatório financeiro do mês passado", False, OTHER, None),
    _case("32", "sou eu. me manda o link da reunião de ontem", False, OTHER, None),
    _case("33", "sim. preciso de ajuda", False, OTHER, None, clarifies=True),
    _case("34", "sou eu. tá dando erro aqui", False, OTHER, None, clarifies=True),
]
"""34 invented conversations. 10 ask for a human; case 29 is a keyword trap ("a pessoa do caixa"). A clear
request no FAQ entry covers goes to the support team with no question (case 31 is a trap for the blank
report entry); only the vague messages 33 and 34 expect one."""

_ATTENDANT = FICTITIOUS["attendants"]["ana"]
_UNIT = FICTITIOUS["units"]["centro"]


def context_for(c: EvalCase, catalog: EvalCatalog) -> TurnContext:
    return TurnContext(
        attendant_name=_ATTENDANT["name"],
        unit_name=_UNIT,
        categories=[PromptCategory(id=x.id, system=x.system, name=x.name) for x in catalog.categories],
        faq_items=catalog.faq_items,
        messages=[PromptMessage(author="bot", text=TEXT.greeting(_ATTENDANT["name"], _UNIT))],
        new_messages=[PromptMessage(author="customer", text=text) for text in c.customer],
        state=TriageState(
            faq_attempted=False,
            clarifications_asked=0,
            unclear_feedback_reasks=0,
            media_prompts=0,
            faq_questions_answered=0,
        ),
        max_clarifications=DEFAULT_RULES.max_clarifications,
        sent_faq=None,
        max_faq_questions=DEFAULT_RULES.max_faq_questions,
    )


@dataclass(frozen=True)
class FaqQuestionCase:
    """A question about the FAQ entry just sent. answer_found: its knowledge base answers it."""

    id: str
    faq: str
    question: str
    answer_found: bool


FAQ_QUESTION_CASES: Final[list[FaqQuestionCase]] = [
    FaqQuestionCase("q1", "password", "o link pra criar a senha nova vale por quanto tempo?", True),
    FaqQuestionCase("q2", "password", "fiz isso mas o e-mail não chegou, o que eu faço?", True),
    FaqQuestionCase("q3", "report", "o relatório do ano inteiro demora mesmo pra abrir?", True),
    FaqQuestionCase("q4", "report", "o relatório mostra venda que ainda não foi confirmada?", True),
    FaqQuestionCase("q5", "password", "dá pra trocar o e-mail do login?", False),
    FaqQuestionCase("q6", "report", "consigo exportar o relatório em PDF?", False),
    FaqQuestionCase("q7", "password", "o painel tem aplicativo pra celular?", False),
    FaqQuestionCase("q8", "reconnect", "e se o QR Code não aparecer no painel?", False),
]
"""Questions after the FAQ entry was sent: 4 answered by its knowledge base and 4 it does not answer,
which must go to a person (one of them about an entry whose knowledge base is empty)."""


def _after_faq_context(faq: str, customer: str, catalog: EvalCatalog) -> TurnContext:
    """The FAQ entry `faq` was just sent, and the customer answers with `customer`."""
    entry = FICTITIOUS["faq"][faq]
    faq_id = next(f.id for f in catalog.faq_items if f.title == entry["title"])
    sent = "\n\n".join([entry["answer_text"], TEXT.faq_follow_up])
    return TurnContext(
        attendant_name=_ATTENDANT["name"],
        unit_name=_UNIT,
        categories=[PromptCategory(id=x.id, system=x.system, name=x.name) for x in catalog.categories],
        faq_items=catalog.faq_items,
        messages=[
            PromptMessage(author="bot", text=TEXT.greeting(_ATTENDANT["name"], _UNIT)),
            PromptMessage(author="customer", text=f"sim. {entry['applies_when']}"),
            PromptMessage(author="bot", text=sent),
        ],
        new_messages=[PromptMessage(author="customer", text=customer)],
        state=TriageState(
            faq_attempted=True,
            clarifications_asked=0,
            unclear_feedback_reasks=0,
            media_prompts=0,
            faq_questions_answered=0,
        ),
        max_clarifications=DEFAULT_RULES.max_clarifications,
        sent_faq=PromptSentFaq(
            id=faq_id, title=entry["title"], answer_text=entry["answer_text"], knowledge_base=entry["knowledge_base"]
        ),
        max_faq_questions=DEFAULT_RULES.max_faq_questions,
    )


def question_context_for(c: FaqQuestionCase, catalog: EvalCatalog) -> TurnContext:
    return _after_faq_context(c.faq, c.question, catalog)


@dataclass(frozen=True)
class FaqFeedbackCase:
    """The customer's answer to the FAQ entry just sent, and the faq_feedback it must get."""

    id: str
    faq: str
    answer: str
    feedback: FaqFeedback


FAQ_FEEDBACK_CASES: Final[list[FaqFeedbackCase]] = [
    FaqFeedbackCase("f1", "password", "não é isso, minha senha tá certa, o problema é outro", "not_resolved"),
    FaqFeedbackCase("f2", "report", "não tem nada a ver, eu perguntei de outra coisa", "not_resolved"),
    FaqFeedbackCase("f3", "reconnect", "não era isso que eu precisava", "not_resolved"),
    FaqFeedbackCase("f4", "password", "deu certo, consegui entrar", "resolved"),
]
"""Answers after the FAQ entry was sent: "that's not it" is not resolved, and goes to a person with no
second question (owner, 2026-10-04); f4 is the control."""


def feedback_context_for(c: FaqFeedbackCase, catalog: EvalCatalog) -> TurnContext:
    return _after_faq_context(c.faq, c.answer, catalog)


IMAGES_DIR: Final = Path(__file__).parent / "images"


@dataclass(frozen=True)
class ImageCase:
    """The customer answers the greeting with an image, and a caption when there is one."""

    id: str
    image: str
    """A PNG in IMAGES_DIR, drawn by scripts/make_eval_images.py."""
    expected: Expected
    caption: str = ""


IMAGE_CASES: Final[list[ImageCase]] = [
    ImageCase("i1", "painel-senha-incorreta.png", Expected(False, LOGIN, PASSWORD)),
    ImageCase("i2", "painel-relatorio-vazio.png", Expected(False, REPORT, BLANK_REPORT)),
    ImageCase("i3", "whatsapp-desconectado.png", Expected(False, WA_DOWN, RECONNECT)),
    ImageCase("i4", "paisagem.png", Expected(False, OTHER, None)),
]
"""Invented screenshots sent alone, for models that read images: the category and FAQ entry must come
from the image. i4 is a drawn landscape, nothing to do with support."""


def load_image(c: ImageCase) -> ImageData:
    return ImageData((IMAGES_DIR / c.image).read_bytes(), "image/png")


def image_context_for(c: ImageCase, catalog: EvalCatalog) -> TurnContext:
    text = " ".join(part for part in (label.image_sent(1), c.caption) if part)
    base = context_for(EvalCase(id=c.id, customer=[text], expected=c.expected), catalog)
    return replace(base, images=(load_image(c),))
