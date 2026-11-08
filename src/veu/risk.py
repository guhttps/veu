"""Risco de identificação pelo contexto: o que sobra num texto e, somado, ainda pode apontar para alguém.

    veu risco texto-protegido.txt

Esconder nomes e documentos não basta quando o texto diz "a gerente de 45 anos da filial de Itu, demitida em
12/03/2026". Cada pista sozinha é comum; juntas, podem identificar a pessoa. Esta análise conta essas pistas
(datas, idades, cidades e cargos) e os dados diretos que ainda estiverem no texto, e dá um nível de risco.
É uma heurística para orientar a revisão, não uma garantia de anonimização.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from veu._text import fold
from veu.recognizers.base import folded_set

_MONTHS = "janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
_DATE = re.compile(
    rf"(?i)\b(?:\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\s+de\s+(?:{_MONTHS})"
    rf"(?:\s+de\s+\d{{4}})?|(?:{_MONTHS})\s+de\s+\d{{4}})\b"
)
_AGE = re.compile(r"(?i)\b\d{1,3}\s*anos(?:\s+de\s+idade)?\b")
_ROLES = (
    "gerente", "diretor", "diretora", "supervisor", "supervisora", "coordenador", "coordenadora", "presidente",
    "medico", "medica", "enfermeiro", "enfermeira", "professor", "professora", "advogado", "advogada", "juiz", "juiza",
    "motorista", "vendedor", "vendedora", "estagiario", "estagiaria", "analista", "engenheiro", "engenheira",
    "contador", "contadora", "secretario", "secretaria", "vereador", "vereadora", "prefeito", "prefeita", "delegado",
    "delegada", "policial", "soldado", "sargento", "capitao", "pastor", "padre", "farmaceutico", "farmaceutica",
)
_ROLE = re.compile(r"(?<![\w])(?:" + "|".join(_ROLES) + r")(?![\w])")
_CAPITALIZED = re.compile(r"[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+){0,3}")


@dataclass
class RiskReport:
    level: str
    direct: Counter = field(default_factory=Counter)
    quasi: Counter = field(default_factory=Counter)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {"nivel": self.level, "identificadores_diretos": dict(self.direct),
                "quase_identificadores": dict(self.quasi), "explicacao": self.explanation}


_cities: frozenset[str] | None = None


def _city_names() -> frozenset[str]:
    global _cities
    if _cities is None:
        _cities = folded_set("ibge_municipios.txt") | folded_set("places.txt")
    return _cities


def assess(text: str, veu=None) -> RiskReport:
    """Conta os dados diretos que sobraram e as pistas indiretas, e dá um nível: baixo, médio ou alto."""
    if veu is None:
        from veu.core import Veu

        veu = Veu()
    direct = Counter(entity.label for entity in veu.analyze(text))
    quasi: Counter = Counter()
    quasi["DATA"] = len(_DATE.findall(text))
    quasi["IDADE"] = len(_AGE.findall(text))
    quasi["CARGO"] = len(_ROLE.findall(fold(text)))
    cities = _city_names()
    quasi["CIDADE"] = sum(1 for match in _CAPITALIZED.finditer(text) if fold(match.group()) in cities)
    quasi = Counter({key: value for key, value in quasi.items() if value})
    kinds = len(quasi)
    if direct:
        level, why = "alto", "ainda há dados que identificam diretamente (" + ", ".join(sorted(direct)) + ")"
    elif kinds >= 3:
        level, why = "alto", "várias pistas juntas (" + ", ".join(sorted(quasi)) + ") podem apontar para uma pessoa"
    elif kinds >= 1:
        level, why = "médio", "há pistas indiretas (" + ", ".join(sorted(quasi)) + "); confira se, juntas, identificam alguém"
    else:
        level, why = "baixo", "nenhum dado direto nem pista indireta comum foi encontrado"
    return RiskReport(level, direct, quasi, why[0].upper() + why[1:] + ".")
