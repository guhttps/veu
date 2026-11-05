"""Funções de texto compartilhadas pelos detectores."""

from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"\s+")
_NON_DIGITS = re.compile(r"\D")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def fold(text: str) -> str:
    """Forma de comparação: minúsculas, sem acentos e com espaços simples."""
    return _SPACES.sub(" ", strip_accents(text).casefold()).strip()


def only_digits(text: str) -> str:
    return _NON_DIGITS.sub("", text)


def words_regex(words) -> re.Pattern | None:
    """Regex que acha qualquer uma das palavras (já normalizadas com fold) como palavra inteira."""
    terms = sorted({fold(word) for word in words if word}, key=len, reverse=True)
    if not terms:
        return None
    return re.compile(r"(?<![\w/])(?:" + "|".join(re.escape(term) for term in terms) + r")(?![\w/])")
