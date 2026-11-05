"""Troca os dados pessoais encontrados por marcadores, substitutos ou máscaras."""

from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass, field

from veu._text import fold
from veu.analyzer import Analyzer
from veu.entities import Entity
from veu.recognizers.base import folded_set
from veu.recognizers.persons import CONNECTORS
from veu.surrogates import make_surrogate
from veu.vault import Vault

OPERATORS = {
    "token": "marcador reversível, como [CPF_1] (padrão)",
    "sintetico": "valor falso do mesmo tipo e formato, reversível (outro CPF válido, outro nome)",
    "mascara": "mascara parte do valor, como ***.982.247-**; não é reversível",
    "remover": "troca pelo tipo, como [CPF]; não é reversível",
    "hash": "marcador estável entre requisições, como [CPF_3fa2c1d9]; reversível com o mesmo cofre",
}
OPERATOR_ALIASES = {"marcador": "token", "sintético": "sintetico", "máscara": "mascara", "synthetic": "sintetico",
                    "mask": "mascara", "redact": "remover"}


def normalize_operator(name: str) -> str:
    key = OPERATOR_ALIASES.get(name.strip().lower(), name.strip().lower())
    if key not in OPERATORS:
        raise ValueError(f'Operador desconhecido: "{name}". Use um destes: {", ".join(OPERATORS)}.')
    return key


@dataclass(frozen=True, slots=True)
class Replacement:
    entity: Entity
    replacement: str
    operator: str

    @property
    def label(self) -> str:
        return self.entity.label

    def to_dict(self) -> dict:
        data = self.entity.to_dict()
        data.pop("texto")
        data["substituto"] = self.replacement
        data["operador"] = self.operator
        return data


@dataclass
class AnonymizationResult:
    text: str
    replacements: list[Replacement]
    vault: Vault = field(repr=False)

    @property
    def entities(self) -> list[Entity]:
        return [item.entity for item in self.replacements]

    def counts(self) -> Counter[str]:
        return Counter(item.label for item in self.replacements)

    def restore(self, text: str) -> str:
        """Restaura um texto produzido a partir deste resultado (por exemplo, a resposta do modelo)."""
        return self.vault.restore(text)


def mask_value(label: str, value: str) -> str:
    if label == "CPF":
        chars = [char for char in value if char.isdigit()]
        if len(chars) == 11:
            visible = set(range(3, 9))
            output, index = [], 0
            for char in value:
                if char.isdigit():
                    output.append(char if index in visible else "*")
                    index += 1
                else:
                    output.append(char)
            return "".join(output)
    if label == "EMAIL" and "@" in value:
        local, domain = value.rsplit("@", 1)
        return f"{local[:1]}***@{domain}"
    if label == "PESSOA":
        return " ".join(word if fold(word) in CONNECTORS else word[:1] + "***" for word in value.split())
    positions = [index for index, char in enumerate(value) if char.isalnum()]
    keep = set(positions[-2:]) if len(positions) > 4 else set()
    return "".join(char if (not char.isalnum() or index in keep) else "*" for index, char in enumerate(value))


class Anonymizer:
    """Anonimiza textos usando um Analyzer e um operador por tipo de dado.

    operator: operador padrão ("token", "sintetico", "mascara", "remover" ou "hash").
    operators: operador por tipo, como {"CARTAO_CREDITO": "remover"}.
    link_names: aplica o marcador de um nome completo também às menções só ao primeiro nome ou ao
    sobrenome ("João da Silva" ... "João" viram o mesmo [PESSOA_1]).
    """

    def __init__(
        self,
        analyzer: Analyzer | None = None,
        *,
        operator: str = "token",
        operators: dict[str, str] | None = None,
        link_names: bool = True,
        secret: bytes | None = None,
    ):
        self.analyzer = analyzer or Analyzer()
        self.operator = normalize_operator(operator)
        self.operators = {label.upper(): normalize_operator(op) for label, op in (operators or {}).items()}
        self.link_names = link_names
        self.secret = secret
        self._ambiguous = folded_set("ambiguous.txt")

    def new_vault(self) -> Vault:
        return Vault(secret=self.secret)

    def anonymize(self, text: str, vault: Vault | None = None) -> AnonymizationResult:
        vault = self.new_vault() if vault is None else vault
        entities = self.analyzer.analyze(text)
        canonical: dict[int, str] = {}
        if self.link_names and entities:
            entities, canonical = self._link_partial_names(text, entities, vault)

        output: list[str] = []
        replacements: list[Replacement] = []
        position = 0
        for entity in entities:
            operator = self.operators.get(entity.label, self.operator)
            replacement = self._replace(entity, operator, vault, canonical.get(entity.start))
            output.append(text[position:entity.start])
            output.append(replacement)
            replacements.append(Replacement(entity, replacement, operator))
            position = entity.end
        output.append(text[position:])
        return AnonymizationResult("".join(output), replacements, vault)

    def _replace(self, entity: Entity, operator: str, vault: Vault, canonical: str | None) -> str:
        value = entity.text
        if canonical is not None and operator in ("token", "hash", "sintetico"):
            # A menção parcial usa o marcador do nome completo, mesmo que ele apareça depois no texto.
            full = Entity(entity.label, entity.start, entity.end, entity.score, canonical, entity.recognizer)
            replacement = self._replace(full, operator, vault, None)
            vault.alias(entity.label, value, replacement)
            return replacement
        if operator == "token":
            return vault.placeholder(entity.label, value)
        if operator == "hash":
            return vault.placeholder(entity.label, value, hashed=True)
        if operator == "sintetico":
            return vault.surrogate(entity.label, value, lambda rng: make_surrogate(entity.label, value, rng))
        if operator == "mascara":
            return mask_value(entity.label, value)
        return f"[{entity.label}]"

    def _link_partial_names(self, text: str, entities: list[Entity], vault: Vault):
        """Acha menções soltas ao primeiro nome ou ao sobrenome de uma pessoa já detectada."""
        parts: dict[str, str] = {}
        for entity in entities:
            if entity.label != "PESSOA":
                continue
            words = [word for word in entity.text.split() if fold(word) not in CONNECTORS]
            if len(words) < 2:
                continue
            for word in (words[0], words[-1]):
                if len(word) >= 3 and fold(word) not in self._ambiguous and word[0].isupper():
                    parts.setdefault(word, entity.text)
        if not parts:
            return entities, {}
        alternatives = "|".join(re.escape(word) for word in sorted(parts, key=len, reverse=True))
        pattern = re.compile(r"(?<![\w])(?:" + alternatives + r")(?![\w])")
        added: list[Entity] = []
        canonical: dict[int, str] = {}
        # As entidades vêm ordenadas e sem sobreposição: busca binária mantém o custo linear em textos grandes.
        starts = [e.start for e in entities]
        ends = [e.end for e in entities]
        for match in pattern.finditer(text):
            position = bisect.bisect_right(starts, match.start())
            if position > 0 and ends[position - 1] > match.start():
                continue
            if position < len(starts) and starts[position] < match.end():
                continue
            entity = Entity("PESSOA", match.start(), match.end(), 0.7, match.group(0), "vinculo")
            added.append(entity)
            canonical[match.start()] = parts[match.group(0)]
        by_folded = {fold(word): full for word, full in parts.items()}
        for entity in entities:
            if entity.label == "PESSOA" and len(entity.text.split()) == 1 and fold(entity.text) in by_folded:
                canonical[entity.start] = by_folded[fold(entity.text)]
        merged = sorted(entities + added, key=lambda e: e.start)
        return merged, canonical
