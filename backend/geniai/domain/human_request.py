"""Keyword check that runs in code before the LLM call (spec §5.3 rule 1), so a human request is
honored even when the LLM is down. Patterns match lowercase text without accents.
"""

import re
import unicodedata
from typing import Final

# re.ASCII keeps `\b` on [A-Za-z0-9_]: a letter NFD cannot strip (such as ø) still ends a word.
HUMAN_REQUEST_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\batendentes?\b", re.ASCII),
    re.compile(r"\bhuman[oa]s?\b", re.ASCII),
    re.compile(r"\bpessoas?\b", re.ASCII),
    re.compile(r"\bfalar com alguem\b", re.ASCII),
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M")).lower()


def mentions_human_request(text: str) -> bool:
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in HUMAN_REQUEST_PATTERNS)
