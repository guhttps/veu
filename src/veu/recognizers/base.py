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


def context_window(text: str, start: int, end: int, before: int, after: int) -> str:
    return fold(text[max(0, start - before):start]) + " │ " + fold(text[end:end + after])
