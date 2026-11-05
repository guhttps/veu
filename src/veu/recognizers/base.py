"""Tipos comuns a todos os detectores."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Protocol

from veu._text import fold


@dataclass(frozen=True, slots=True)
class Candidate:
    """Trecho que um detector acha que é um dado pessoal, com uma pontuação de 0 a 1."""

    label: str
    start: int
    end: int
    score: float
    recognizer: str


class Recognizer(Protocol):
    name: str
    labels: frozenset[str]

    def find(self, text: str) -> Iterable[Candidate]: ...


@cache
def load_wordlist(name: str) -> tuple[str, ...]:
    """Lê uma lista de veu/data, ignorando linhas vazias e comentários."""
    content = resources.files("veu").joinpath("data", name).read_text(encoding="utf-8")
    entries = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return tuple(dict.fromkeys(entries))


@cache
def folded_set(name: str) -> frozenset[str]:
    return frozenset(fold(entry) for entry in load_wordlist(name))


def text_before(text: str, start: int, size: int) -> str:
    """Até size caracteres antes de start, sem começar no meio de uma palavra.

    Cortar "example.org" em "rg" faria a palavra de contexto "RG" aparecer onde não existe.
    """
    left = max(0, start - size)
    if left > 0 and text[left - 1].isalnum():
        while left < start and text[left].isalnum():
            left += 1
    return text[left:start]


def text_after(text: str, end: int, size: int) -> str:
    """Até size caracteres depois de end, sem terminar no meio de uma palavra."""
    right = min(len(text), end + size)
    if right < len(text) and text[right].isalnum():
        while right > end and text[right - 1].isalnum():
            right -= 1
    return text[end:right]


def context_window(text: str, start: int, end: int, before: int, after: int) -> str:
    return fold(text_before(text, start, before)) + " │ " + fold(text_after(text, end, after))
