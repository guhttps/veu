"""Junta os detectores, filtra pela pontuação e resolve sobreposições."""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable

from veu._text import fold, only_digits
from veu.cache import DetectionCache
from veu.entities import Entity
from veu.recognizers import (
    AddressRecognizer,
    Candidate,
    PatternRecognizer,
    PersonRecognizer,
    Recognizer,
    SecretRecognizer,
)
from veu.validators import normalize_cnpj

DEFAULT_THRESHOLD = 0.5


def default_recognizers() -> list[Recognizer]:
    return [PatternRecognizer(), PersonRecognizer(), AddressRecognizer(), SecretRecognizer()]


class Analyzer:
    """Encontra dados pessoais em um texto.

    threshold: pontuação mínima (0 a 1). O padrão 0,5 privilegia a privacidade: valores com formato
    de documento, mas dígitos verificadores errados, também são escondidos.
    labels: limita a detecção a alguns tipos (por padrão, todos).
    allowlist: valores que nunca são escondidos, como o CNPJ ou o e-mail de contato da própria empresa.
    cache: guarda o resultado de textos longos já analisados (veja veu.cache). None desliga.
    """

    def __init__(
        self,
        recognizers: Iterable[Recognizer] | None = None,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        labels: Iterable[str] | None = None,
        allowlist: Iterable[str] = (),
        allow_patterns: Iterable[str] = (),
        cache: DetectionCache | None = None,
    ):
        self.cache = cache
        self.recognizers = list(default_recognizers() if recognizers is None else recognizers)
        self.threshold = threshold
        self.labels = {label.upper() for label in labels} if labels else None
        allowlist = list(allowlist)
        self._allow_text = {fold(value) for value in allowlist}
        self._allow_codes = {only_digits(value) for value in allowlist if len(only_digits(value)) >= 6}
        self._allow_codes |= {normalize_cnpj(value) for value in allowlist if len(normalize_cnpj(value)) == 14}
        self._allow_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in allow_patterns]
        self._has_allowlist = bool(self._allow_text or self._allow_codes or self._allow_patterns)

    def _allowed(self, value: str) -> bool:
        if fold(value) in self._allow_text:
            return True
        if any(pattern.search(value) for pattern in self._allow_patterns):
            return True
        digits = only_digits(value)
        return (len(digits) >= 6 and digits in self._allow_codes) or normalize_cnpj(value) in self._allow_codes

    def candidates(self, text: str, threshold: float | None = None) -> list[Candidate]:
        minimum = self.threshold if threshold is None else threshold
        found = []
        for recognizer in self.recognizers:
            for candidate in recognizer.find(text):
                if candidate.score < minimum:
                    continue
                if self.labels is not None and candidate.label not in self.labels:
                    continue
                if self._has_allowlist and self._allowed(text[candidate.start:candidate.end]):
                    continue
                found.append(candidate)
        return found

    def analyze(self, text: str, threshold: float | None = None) -> list[Entity]:
        if not text:
            return []
        cache = self.cache if self.cache is not None and self.cache.usable(text) else None
        extra = "" if threshold is None else str(threshold)
        if cache is not None:
            spans = cache.get(text, extra)
            if spans is not None:
                return [Entity(label, start, end, score, text[start:end], recognizer)
                        for label, start, end, score, recognizer in spans]
        chosen = resolve_overlaps(self.candidates(text, threshold))
        if cache is not None:
            cache.put(text, tuple((c.label, c.start, c.end, c.score, c.recognizer) for c in chosen), extra)
        return [
            Entity(c.label, c.start, c.end, c.score, text[c.start:c.end], c.recognizer)
            for c in chosen
        ]


def resolve_overlaps(candidates: list[Candidate]) -> list[Candidate]:
    """Escolhe um candidato por trecho.

    1. Um candidato contido em outro maior é descartado (o endereço "Rua João Pessoa, 50" vence a pessoa
       "João Pessoa"; o telefone com DDD vence o número local dentro dele).
    2. Nas sobreposições parciais e nos trechos idênticos, vence a maior pontuação e, no empate, o mais longo.
    """
    ordered = sorted(candidates, key=lambda c: (c.start, -c.end, -c.score))
    uncontained: list[Candidate] = []
    container: Candidate | None = None
    for candidate in ordered:
        if (
            container is not None
            and candidate.end <= container.end
            and (candidate.start, candidate.end) != (container.start, container.end)
        ):
            continue
        uncontained.append(candidate)
        if container is None or candidate.end > container.end:
            container = candidate

    starts: list[int] = []
    ends: list[int] = []
    chosen: list[Candidate] = []
    for candidate in sorted(uncontained, key=lambda c: (-c.score, -(c.end - c.start), c.start)):
        position = bisect.bisect_left(starts, candidate.start)
        if position > 0 and ends[position - 1] > candidate.start:
            continue
        if position < len(starts) and starts[position] < candidate.end:
            continue
        starts.insert(position, candidate.start)
        ends.insert(position, candidate.end)
        chosen.append(candidate)
    return sorted(chosen, key=lambda c: c.start)
