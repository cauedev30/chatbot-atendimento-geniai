"""Whether the first messages of a ticket are only a greeting (spec §5.1 step 3). The greeting then asks
for the problem; otherwise the customer already said something, and it only asks to confirm who they are.
Words are compared in lowercase without accents, punctuation or emoji.
"""

import re
import unicodedata
from collections.abc import Sequence
from typing import Final

GREETING_WORDS: Final[frozenset[str]] = frozenset(
    {
        "oi",
        "oie",
        "ola",
        "opa",
        "eai",
        "e",
        "ai",
        "alo",
        "bom",
        "boa",
        "dia",
        "tarde",
        "noite",
        "tudo",
        "bem",
        "td",
        "blz",
        "beleza",
        "salve",
        "hello",
        "hi",
        "pessoal",
        "gente",
        "suporte",
        "geniai",
    }
)

# Anything but a lowercase ASCII letter or digit (punctuation, emoji, spaces) separates words.
_SEPARATORS: Final = re.compile(r"[^a-z0-9]+")


def _words(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M")).lower()
    return [w for w in _SEPARATORS.split(plain) if w]


def is_bare_greeting(texts: Sequence[str], *, has_media: bool) -> bool:
    """True when every word of the texts is a greeting word, or there is no text. A photo, an audio, a
    video or a file is content."""
    if has_media:
        return False
    return all(word in GREETING_WORDS for text in texts for word in _words(text))
