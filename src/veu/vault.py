"""Cofre: guarda o mapeamento entre os marcadores e os dados reais e restaura textos.

O cofre fica só na memória do processo (ou no arquivo que você salvar pela CLI) e nunca é
enviado ao modelo de IA.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
from collections import Counter
from dataclasses import dataclass

from veu._text import fold, only_digits

# Rótulos cujos valores são comparados só pelos dígitos ("529.982.247-25" e "52998224725" são o mesmo CPF).
DIGIT_LABELS = frozenset({
    "CPF", "TELEFONE", "CEP", "CARTAO_CREDITO", "PIS", "CNS", "CNH", "TITULO_ELEITOR", "RENAVAM",
    "CONTA_BANCARIA", "PROCESSO",
})
CODE_LABELS = frozenset({"CNPJ", "RG", "PLACA", "PASSAPORTE", "CHAVE_PIX"})

# O colchete final é opcional: modelos às vezes escrevem "[CPF_1" ou "[CPF 1]".
_PLACEHOLDER = r"\[\s*(?P<ph_label>[A-Za-z]+(?:_[A-Za-z]+)*)[_\s-]+(?P<ph_id>[0-9A-Fa-f]{1,8})(?:\s*\]|(?![\w]))"
_BARE = r"(?<![\w\[])(?P<bare_label>[A-Z]+(?:_[A-Z]+)*)_(?P<bare_id>\d{1,6}|[0-9a-f]{8})(?![\w\]])"
_TRAILING_WORD = re.compile(r"[A-Za-z0-9_]+$")
_DIGIT_SEPARATOR = r"[\s.\-/()]*"
MAX_HOLDBACK = 48


def normalize_value(label: str, value: str) -> str:
    """Forma canônica de um valor, usada para dar o mesmo marcador a grafias diferentes."""
    if label == "TELEFONE":
        digits = only_digits(value)
        return digits[2:] if len(digits) in (12, 13) and digits.startswith("55") else digits
    if label in DIGIT_LABELS:
        return only_digits(value) or fold(value)
    if label in CODE_LABELS:
        return re.sub(r"[^0-9A-Za-z]", "", value).upper()
    if label == "EMAIL":
        return value.strip().casefold()
    return fold(value)


@dataclass(frozen=True, slots=True)
class VaultEntry:
    label: str
    original: str
    replacement: str
    kind: str  # "marcador" ou "sintetico"


class Vault:
    """Mapeamento reversível entre dados reais e o que foi enviado ao modelo."""

    def __init__(self, secret: bytes | None = None, seed: int | None = None):
        self._by_key: dict[tuple[str, str], str] = {}
        self._entries: dict[str, VaultEntry] = {}
        self._counters: Counter[str] = Counter()
        self._secret = secret or os.urandom(32)
        self.rng = random.Random(seed)
        self._pattern: re.Pattern | None = None
        self._digit_surrogates: dict[str, str] = {}
        self._text_surrogates: dict[str, str] = {}

    # Criação de marcadores
    def lookup(self, label: str, value: str) -> str | None:
        return self._by_key.get((label, normalize_value(label, value)))

    def placeholder(self, label: str, value: str, *, hashed: bool = False) -> str:
        key = (label, normalize_value(label, value))
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        if hashed:
            digest = hmac.new(self._secret, f"{label}:{key[1]}".encode(), hashlib.sha256).hexdigest()
            replacement = f"[{label}_{digest[:8]}]"
        else:
            self._counters[label] += 1
            replacement = f"[{label}_{self._counters[label]}]"
        self._store(key, VaultEntry(label, value, replacement, "marcador"))
        return replacement

    def surrogate(self, label: str, value: str, make) -> str:
        """Substituto sintético e verossímil (por exemplo, outro CPF válido). make(rng) gera o valor."""
        key = (label, normalize_value(label, value))
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        taken = {fold(entry.original) for entry in self._entries.values()} | {fold(r) for r in self._entries}
        for _ in range(20):
            replacement = make(self.rng)
            if replacement and fold(replacement) not in taken and fold(replacement) != fold(value):
                break
        else:
            return self.placeholder(label, value)
        self._store(key, VaultEntry(label, value, replacement, "sintetico"))
        return replacement

    def alias(self, label: str, value: str, replacement: str) -> None:
        """Faz outro valor (por exemplo, só o primeiro nome) usar um marcador já existente."""
        self._by_key.setdefault((label, normalize_value(label, value)), replacement)

    def _store(self, key: tuple[str, str], entry: VaultEntry) -> None:
        self._by_key[key] = entry.replacement
        self._entries[entry.replacement] = entry
        if entry.kind == "sintetico":
            if entry.label in DIGIT_LABELS:
                self._digit_surrogates[only_digits(entry.replacement)] = entry.original
            else:
                self._text_surrogates[fold(entry.replacement)] = entry.original
        self._pattern = None

    # Consulta
    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True

    def entries(self) -> list[VaultEntry]:
        return list(self._entries.values())

    @property
    def labels(self) -> set[str]:
        return {entry.label for entry in self._entries.values()}

    @property
    def has_placeholders(self) -> bool:
        return any(entry.kind == "marcador" for entry in self._entries.values())

    # Restauração
    def _compiled(self) -> re.Pattern:
        if self._pattern is None:
            parts = [_PLACEHOLDER, _BARE]
            surrogates = []
            for entry in self._entries.values():
                if entry.kind != "sintetico":
                    continue
                if entry.label in DIGIT_LABELS:
                    digits = only_digits(entry.replacement)
                    surrogates.append(r"(?<!\d)" + _DIGIT_SEPARATOR.join(digits) + r"(?!\d)")
                else:
                    words = [re.escape(word) for word in entry.replacement.split()]
                    surrogates.append(r"(?<![\w@.])(?i:" + r"\s+".join(words) + r")(?![\w@])")
            if surrogates:
                surrogates.sort(key=len, reverse=True)
                parts.append("(?P<sur>" + "|".join(surrogates) + ")")
            self._pattern = re.compile("|".join(parts))
        return self._pattern

    def _original_for(self, match: re.Match) -> str | None:
        if match.group("ph_label"):
            key = f"[{match.group('ph_label').upper()}_{match.group('ph_id').lower()}]"
        elif match.group("bare_label"):
            key = f"[{match.group('bare_label')}_{match.group('bare_id')}]"
        else:
            text = match.group(0)
            return self._digit_surrogates.get(only_digits(text)) or self._text_surrogates.get(fold(text))
        entry = self._entries.get(key)
        return entry.original if entry and entry.kind == "marcador" else None

    def restore(self, text: str, *, json_escape: bool = False) -> str:
        """Troca marcadores e substitutos pelos valores reais.

        json_escape: use quando o texto é um pedaço de JSON (argumentos de chamadas de ferramenta).
        """
        if not text or not self._entries:
            return text

        def replace(match: re.Match) -> str:
            original = self._original_for(match)
            if original is None:
                return match.group(0)
            return json.dumps(original, ensure_ascii=False)[1:-1] if json_escape else original

        return self._compiled().sub(replace, text)

    def restorer(self, *, json_escape: bool = False) -> StreamRestorer:
        return StreamRestorer(self, json_escape=json_escape)

    def _might_continue(self, tail: str) -> bool:
        """O fim do texto pode ser o começo de um marcador ou substituto que chega no próximo pedaço?"""
        upper = tail.upper()
        if _TRAILING_WORD.fullmatch(tail):
            for label in self.labels:
                prefix = label + "_"
                if prefix.startswith(upper) or upper.startswith(prefix):
                    return True
        folded = fold(tail)
        if folded and any(surrogate.startswith(folded) for surrogate in self._text_surrogates):
            return True
        digits = only_digits(tail)
        if digits and re.fullmatch(r"[\d\s.\-/()]+", tail):
            return any(surrogate.startswith(digits) for surrogate in self._digit_surrogates)
        return False

    def max_surrogate_length(self) -> int:
        return max((len(entry.replacement) for entry in self._entries.values() if entry.kind == "sintetico"),
                   default=0)

    # Persistência (a CLI salva o cofre para restaurar depois). O arquivo contém os dados reais.
    def to_dict(self) -> dict:
        return {
            "versao": 1,
            "itens": [
                {"entidade": e.label, "original": e.original, "substituto": e.replacement, "tipo": e.kind}
                for e in self._entries.values()
            ],
            "chaves": [{"entidade": label, "valor": value, "substituto": rep} for (label, value), rep in self._by_key.items()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Vault:
        vault = cls()
        for item in data.get("itens", []):
            entry = VaultEntry(item["entidade"], item["original"], item["substituto"], item.get("tipo", "marcador"))
            vault._store((entry.label, normalize_value(entry.label, entry.original)), entry)
            match = re.fullmatch(r"\[[A-Z_]+_(\d+)\]", entry.replacement)
            if match:
                vault._counters[entry.label] = max(vault._counters[entry.label], int(match.group(1)))
        for item in data.get("chaves", []):
            vault._by_key.setdefault((item["entidade"], item["valor"]), item["substituto"])
        return vault


class StreamRestorer:
    """Restaura uma resposta que chega em pedaços (streaming).

    Um marcador pode chegar dividido ("[PES" + "SOA_1]"): o fim de cada pedaço que ainda pode
    virar um marcador fica retido até o próximo pedaço, ou até flush().
    """

    def __init__(self, vault: Vault, *, json_escape: bool = False):
        self.vault = vault
        self.json_escape = json_escape
        self._buffer = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buffer += text
        cut = self._safe_cut(self._buffer)
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self.vault.restore(ready, json_escape=self.json_escape)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self.vault.restore(ready, json_escape=self.json_escape)

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    def _safe_cut(self, text: str) -> int:
        cut = len(text)
        bracket = text.rfind("[")
        if bracket != -1 and "]" not in text[bracket:] and len(text) - bracket <= MAX_HOLDBACK:
            cut = bracket
        longest = min(len(text), max(MAX_HOLDBACK, self.vault.max_surrogate_length()))
        for size in range(longest, 0, -1):
            start = len(text) - size
            if start >= cut:
                break
            if start > 0 and text[start - 1].isalnum() and text[start].isalnum():
                continue
            if self.vault._might_continue(text[start:]):
                cut = start
                break
        return cut
