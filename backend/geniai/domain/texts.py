"""Fixed customer-facing texts (Brazilian Portuguese). The LLM never writes these."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class _Texts:
    unidentified_ack: str = "Recebemos sua mensagem! A equipe de suporte já fala com você."
    handoff: str = "Certo! Vou passar sua conversa para a nossa equipe, que já fala com você por aqui."
    faq_follow_up: str = "Isso resolveu o seu problema? Responda sim ou não."
    reask_feedback: str = "Só pra eu confirmar: as instruções resolveram o problema? Responda sim ou não."
    resolved_thanks: str = "Que bom que resolveu! Se precisar, é só chamar."
    ask_for_text: str = (
        "Ainda não consigo ouvir áudios nem abrir imagens ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    clarify_fallback: str = "Pode me contar um pouco mais sobre o problema?"

    @staticmethod
    def greeting(name: str, unit: str) -> str:
        return (
            f"Olá! Aqui é o suporte da GeniAI. Falo com {name}, da unidade {unit}? "
            "Se for isso mesmo, me conta qual é o problema."
        )


TEXT: Final = _Texts()

MEDIA_PLACEHOLDER: Final = "[mídia]"
"""Stored as the text of a media-only message."""


def category_label(system: str, name: str) -> str:
    return f"{system} / {name}"


def truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else f"{text[: max_len - 1]}…"
