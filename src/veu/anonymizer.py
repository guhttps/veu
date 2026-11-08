"""Troca os dados pessoais encontrados por marcadores, substitutos ou máscaras."""

from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass, field

from veu._text import fold
from veu.analyzer import Analyzer
from veu.entities import SECRET_LABELS, Entity
from veu.recognizers.base import folded_set
from veu.recognizers.persons import CONNECTORS
from veu.recognizers.secrets import secret_prefix
from veu.surrogates import make_surrogate
from veu.vault import RestorePolicy, Vault

OPERATORS = {
    "token": "marcador reversível, como [CPF_1] (padrão)",
    "sintetico": "valor falso do mesmo tipo e formato, reversível (outro CPF válido, outro nome)",
    "mascara": "mascara parte do valor, como ***.982.247-**; não é reversível",
    "remover": "troca pelo tipo, como [CPF]; não é reversível",
    "hash": "marcador estável entre requisições, como [CPF_3fa2c1d9]; reversível com o mesmo cofre",
    "generalizar": "guarda só o que serve para análise (ano de nascimento, região do CEP, DDD, rede do IP) e troca o "
                   "resto pelo tipo; não é reversível",
}
OPERATOR_ALIASES = {"marcador": "token", "sintético": "sintetico", "máscara": "mascara", "synthetic": "sintetico",
                    "mask": "mascara", "redact": "remover", "generalize": "generalizar"}


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
    if label in ("SENHA", "CHAVE_PRIVADA"):
        return "********"
    if label == "URL_CONEXAO" and "://" in value:
        return value.split("://", 1)[0] + "://****"
    if label in SECRET_LABELS:
        return secret_prefix(value) + "****"
    positions = [index for index, char in enumerate(value) if char.isalnum()]
    keep = set(positions[-2:]) if len(positions) > 4 else set()
    return "".join(char if (not char.isalnum() or index in keep) else "*" for index, char in enumerate(value))


# Palavras de nome (letras, com apóstrofo): a mesma definição do detector de nomes.
_NAME_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿ]+)*")


def _find_names(text: str, parts: dict[str, str]):
    """(início, fim) das sequências de palavras cuja forma normalizada está em parts (a mais longa primeiro).

    Equivale a casar cada nome em qualquer caixa e com ou sem acento, separado por espaços, com custo linear.
    """
    longest = max(len(key.split()) for key in parts)
    words = [(m.start(), m.end(), fold(m.group())) for m in _NAME_WORD.finditer(text)]
    index = 0
    while index < len(words):
        for size in range(min(longest, len(words) - index), 0, -1):
            chunk = words[index:index + size]
            if any(not text[a[1]:b[0]].isspace() for a, b in zip(chunk, chunk[1:], strict=False)):
                continue
            start, end = chunk[0][0], chunk[-1][1]
            if (start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_")) or (
                    end < len(text) and (text[end].isalnum() or text[end] == "_")):
                continue
            if " ".join(word for _, _, word in chunk) in parts:
                yield start, end
                index += size
                break
        else:
            index += 1


def generalize_value(label: str, value: str) -> str:
    """Versão menos precisa do valor, que ainda serve para análises (idade, região) e identifica menos."""
    from veu.validators import parse_date

    digits = re.sub(r"\D", "", value)
    if label == "DATA_NASCIMENTO":
        parsed = parse_date(value)
        if parsed is not None:
            return str(parsed.year)
    elif label == "CEP" and len(digits) == 8:
        return f"{digits[:5]}-***"
    elif label == "TELEFONE":
        country = re.match(r"\s*\+(\d{1,3})", value)
        if country and country.group(1) != "55":
            return f"+{country.group(1)} ****"
        local = digits[2:] if len(digits) in (12, 13) and digits.startswith("55") else digits
        if len(local) in (10, 11):
            return f"({local[:2]}) ****-****"
    elif label == "IP":
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
            return ".".join(value.split(".")[:3]) + ".0/24"
        if ":" in value:
            import ipaddress

            try:
                network = ipaddress.ip_network(f"{value}/48", strict=False)
            except ValueError:
                pass
            else:
                return str(network)
    return f"[{label}]"


class Anonymizer:
    """Anonimiza textos usando um Analyzer e um operador por tipo de dado.

    operator: operador padrão ("token", "sintetico", "mascara", "remover" ou "hash").
    operators: operador por tipo, como {"CARTAO_CREDITO": "remover"}.
    link_names: aplica o marcador de um nome completo também às menções só ao primeiro nome ou ao
    sobrenome ("João da Silva" ... "João" viram o mesmo [PESSOA_1]).
    policy: onde a restauração pode devolver os dados reais (veja veu.vault.RestorePolicy).
    """

    def __init__(
        self,
        analyzer: Analyzer | None = None,
        *,
        operator: str = "token",
        operators: dict[str, str] | None = None,
        link_names: bool = True,
        secret: bytes | None = None,
        policy: RestorePolicy | None = None,
    ):
        self.analyzer = analyzer or Analyzer()
        self.operator = normalize_operator(operator)
        self.operators = {label.upper(): normalize_operator(op) for label, op in (operators or {}).items()}
        self.link_names = link_names
        self.secret = secret
        self.policy = policy or RestorePolicy()
        # Nomes ambíguos revistos à mão ("Rosa", "Luz") não se propagam; os que o dicionário marca como palavras
        # ("Costa", "Nascimento") só se propagam com inicial maiúscula.
        self._ambiguous = folded_set("ambiguous.txt")
        self._capitalized_only = folded_set("ibge_ambiguos.txt") - self._ambiguous

    def new_vault(self) -> Vault:
        return Vault(secret=self.secret, policy=self.policy)

    def anonymize(self, text: str, vault: Vault | None = None, *, neutralize: bool = True) -> AnonymizationResult:
        """neutralize: desarma marcadores que já vêm no texto ([CPF_1] vira [CPF#1]), para que um marcador
        escrito por outra pessoa nunca vire um dado real na restauração."""
        vault = self.new_vault() if vault is None else vault
        if neutralize:
            text = vault.neutralize(text)
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

    def replace_value(self, label: str, value: str, vault: Vault) -> str:
        """Substitui um valor inteiro já sabido ser de um tipo (ex.: toda a coluna "cpf" de uma planilha)."""
        label = label.upper()
        operator = self.operators.get(label, self.operator)
        return self._replace(Entity(label, 0, len(value), 1.0, value, "forcado"), operator, vault, None)

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
        if operator == "generalizar":
            return generalize_value(entity.label, value)
        return f"[{entity.label}]"

    def _link_partial_names(self, text: str, entities: list[Entity], vault: Vault):
        """Propaga nomes já detectados no mesmo texto.

        Menções soltas ao primeiro nome, ao sobrenome ou ao nome inteiro, em qualquer caixa e com ou sem acento
        ("Rayane Souza" ... "kkkk a rayane esqueceu", "RAYANE SOUZA"), recebem o mesmo marcador do nome completo.
        Nomes ambíguos ("Rosa", "Luz") não se propagam.
        """
        parts: dict[str, str] = {}  # forma normalizada (fold) -> nome completo
        # Nomes completos primeiro: "Ana" sozinho, antes de "Ana Beatriz Moura", usa o marcador do nome completo.
        for entity in sorted(entities, key=lambda e: -len(e.text.split())):
            if entity.label != "PESSOA" or entity.score < 0.6:
                continue
            words = [word for word in entity.text.split() if fold(word) not in CONNECTORS]
            if not words:
                continue
            if len(words) >= 2:
                parts.setdefault(fold(entity.text), entity.text)
                linked = [word for word in (words[0], words[-1]) if word[0].isupper()]
            else:
                linked = words
            for word in linked:
                if len(word) >= 3 and fold(word) not in self._ambiguous:
                    parts.setdefault(fold(word), entity.text)
        if not parts:
            return entities, {}
        added: list[Entity] = []
        canonical: dict[int, str] = {}
        # As entidades vêm ordenadas e sem sobreposição: busca binária mantém o custo linear em textos grandes.
        starts = [e.start for e in entities]
        ends = [e.end for e in entities]
        for start, end in _find_names(text, parts):
            position = bisect.bisect_right(starts, start)
            if position > 0 and ends[position - 1] > start:
                continue
            if position < len(starts) and starts[position] < end:
                continue
            key = fold(text[start:end])
            if key in self._capitalized_only and not text[start].isupper():
                continue  # "Costa" é a pessoa; "costa" (o litoral) e "data de nascimento", não
            added.append(Entity("PESSOA", start, end, 0.7, text[start:end], "vinculo"))
            canonical[start] = parts[key]
        for entity in entities:
            full = parts.get(fold(entity.text)) if entity.label == "PESSOA" else None
            if full is not None and full != entity.text:
                canonical[entity.start] = full
        merged = sorted(entities + added, key=lambda e: e.start)
        return merged, canonical
