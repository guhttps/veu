"""Listas próprias: termos que sempre são escondidos (nomes de clientes, projetos e produtos da empresa).

A busca ignora maiúsculas e acentos ("Joana Prado" acha "JOANA PRADO" e "joana prado") e respeita palavras
inteiras ("Ana" não acha "Banana"). Espaços no termo aceitam qualquer espaço no texto.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

from veu.recognizers.base import Candidate


class _FoldTable(dict):
    """Tabela do str.translate: cada caractere vira um só (minúsculo, sem acento), e as posições não mudam."""

    def __missing__(self, code: int) -> str:
        char = chr(code)
        base = unicodedata.normalize("NFD", char)[0].lower()
        self[code] = value = base if len(base) == 1 else char
        return value


_FOLD = _FoldTable()


def fold_keeping_positions(text: str) -> str:
    return text.translate(_FOLD)


def _term_pattern(term: str) -> str:
    return r"\s+".join(re.escape(part) for part in fold_keeping_positions(term).split())


class TermRecognizer:
    """Acha os termos das listas próprias: {"PESSOA": ["Joana Prado"], "TERMO": ["Projeto Netuno"]}."""

    name = "termos"

    def __init__(self, terms: Mapping[str, Iterable[str]]):
        self.patterns: list[tuple[str, re.Pattern]] = []
        for label, values in terms.items():
            parts = sorted({_term_pattern(value) for value in values if len(value.strip()) >= 2}, key=len, reverse=True)
            if parts:
                self.patterns.append((label.upper(), re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])")))
        self.labels = frozenset(label for label, _ in self.patterns)

    def find(self, text: str) -> Iterable[Candidate]:
        if not self.patterns:
            return
        folded = fold_keeping_positions(text)
        for label, pattern in self.patterns:
            for match in pattern.finditer(folded):
                yield Candidate(label, match.start(), match.end(), 0.99, self.name)
