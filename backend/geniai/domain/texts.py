"""Fixed customer-facing texts (Brazilian Portuguese). The LLM never writes these."""

from dataclasses import dataclass
from typing import Final

from geniai.domain.types import UnreadMedia


@dataclass(frozen=True)
class _Texts:
    unidentified_ack: str = "Recebemos sua mensagem! A equipe de suporte vai te responder por aqui."
    handoff: str = "Certo! Passei sua conversa para a nossa equipe, que vai te responder por aqui."
    faq_follow_up: str = "Isso resolveu o seu problema? Responda sim ou não."
    reask_feedback: str = "Só pra eu confirmar: as instruções resolveram o problema? Responda sim ou não."
    resolved_thanks: str = "Que bom que resolveu! Se precisar, é só chamar."
    ask_for_text: str = (
        "Ainda não consigo ouvir áudios nem abrir imagens ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    """Image reading off (LLM_READS_IMAGES=false)."""
    ask_for_text_image: str = "Não consegui abrir a imagem. Pode escrever o problema em texto, por favor?"
    """OWNER-UNCONFIRMED wording: only images, none of which opened."""
    ask_for_text_other: str = (
        "Ainda não consigo ouvir áudios nem abrir vídeos ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    """OWNER-UNCONFIRMED wording: an audio, a video or a file, with image reading on."""
    clarify_fallback: str = "Pode me contar um pouco mais sobre o problema?"

    def ask_for_text_for(self, unread: UnreadMedia) -> str:
        return {"media": self.ask_for_text, "image": self.ask_for_text_image, "other": self.ask_for_text_other}[unread]

    @staticmethod
    def greeting(name: str, unit: str) -> str:
        """The first messages are only a greeting (domain/greeting.py): the bot asks for the problem."""
        return (
            f"Olá! Aqui é o suporte da GeniAI. Falo com {name}, da unidade {unit}? "
            "Se for isso mesmo, me conta qual é o problema."
        )

    @staticmethod
    def greeting_with_content(name: str, unit: str) -> str:
        """The first messages already said something (domain/greeting.py): the bot uses it once confirmed."""
        return (
            f"Olá! Aqui é o suporte da GeniAI. Falo com {name}, da unidade {unit}? "
            "Se for isso mesmo, é só confirmar que eu já vejo o que você mandou."
        )


TEXT: Final = _Texts()

MEDIA_PLACEHOLDER: Final = "[mídia]"
"""Stored as the text of a media-only message."""


def category_label(system: str, name: str) -> str:
    return f"{system} / {name}"


def with_unanswered_question(summary: str, question: str) -> str:
    """The card summary of a handoff on a question about the FAQ entry that the bot did not answer."""
    return f"{summary.strip()} Dúvida sem resposta: {truncate(question.strip(), 280)}".strip()


def truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else f"{text[: max_len - 1]}…"
