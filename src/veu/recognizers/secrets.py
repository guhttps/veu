"""Segredos: chaves de API, tokens, senhas, chaves privadas e URLs de conexão com senha.

Os formatos com prefixo conhecido (sk-, ghp_, AKIA...) ficam em data/segredos.json, o mesmo arquivo usado
pela versão em JavaScript. Aqui ficam as regras genéricas, que olham o nome do campo (API_KEY=..., senha: ...).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources

from veu.recognizers.base import Candidate

LABELS = ("CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO")


@dataclass(frozen=True)
class SecretRule:
    id: str
    label: str
    pattern: re.Pattern
    score: float
    group: int = 0
    filter: str | None = None
    trim: str = ""


@cache
def load_rules() -> tuple[SecretRule, ...]:
    raw = json.loads(resources.files("veu").joinpath("data", "segredos.json").read_text(encoding="utf-8"))
    return tuple(
        SecretRule(
            rule["id"], rule["entidade"], re.compile(rule["padrao"]), float(rule["pontuacao"]),
            int(rule.get("grupo", 0)), rule.get("filtro"), rule.get("aparar", ""),
        )
        for rule in raw["regras"]
    )


# Atribuições: chave, separador e valor (API_KEY=..., "token": "...", senha: ..., X-Api-Key: ...).
VALUE_CHARS = r"[^\s\"'`,;&<>()\[\]{}]"
ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_.-]{0,60})[\"']?[ \t]*(=>|:=|=|:)[ \t]*[\"']?(" + VALUE_CHARS + r"{3,500})"
)
# Prosa: "a senha é Gato2024", "senha do wifi: casa1234".
PROSE_PASSWORD = re.compile(
    r"(?<![A-Za-z0-9])(?:senha|password|passwd)(?:[^\n:=]{0,25}?)(\s*(?::|=)\s*|\s+(?:é|eh|is)\s+)[\"']?("
    + VALUE_CHARS + r"{3,200})",
    re.IGNORECASE,
)

PASSWORD_WORDS = frozenset({"password", "passwd", "passphrase", "pwd", "senha", "pass", "passw"})
SECRET_WORDS = frozenset({"secret", "token", "apikey", "credential", "credentials", "credencial", "credenciais"})
SECRET_PAIRS = frozenset({
    ("api", "key"), ("access", "key"), ("private", "key"), ("secret", "key"), ("auth", "key"), ("chave", "api"),
    ("signing", "key"), ("encryption", "key"), ("master", "key"), ("account", "key"), ("app", "key"),
})
# Campos que têm "token" ou "secret" no nome mas não guardam o segredo.
NOT_SECRET_WORDS = frozenset({
    "url", "uri", "endpoint", "path", "file", "filename", "name", "type", "count", "limit", "length", "size", "ttl",
    "expires", "expiry", "expiration", "max", "min", "header", "field", "label", "prefix", "env", "var",
    "placeholder", "hint", "description", "desc", "enabled", "required", "policy", "rotation", "version", "tokens",
    "usage", "id", "ref", "arn", "mode", "format", "manager", "provider", "store", "location", "nome",
    "tipo", "arquivo", "caminho",
})
PLACEHOLDERS = frozenset({
    "null", "none", "nil", "true", "false", "undefined", "empty", "vazio", "string", "str", "number", "int",
    "bool", "boolean", "any", "text", "texto", "required", "optional", "hidden", "secret", "password", "senha",
    "token", "redacted", "removido", "removida", "omitido", "omitida", "masked", "default",
})
_IDENTIFIER_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
_CONSTANT = re.compile(r"[A-Z_]+")
_FILLER = re.compile(r"[*xX.•_#-]+")
_RANDOM_RUN = re.compile(r"[A-Za-z0-9+/=_-]{8,}")


_PREFIX = re.compile(r"(?:AKIA|ASIA|ABIA|ACCA|AIza|GOCSPX-|ya29\.|eyJ|SG\.|\$aact_|(?:[A-Za-z]{2,10}[_-]){1,2})")


def secret_prefix(value: str) -> str:
    """Prefixo que identifica o tipo da chave sem revelar o segredo ("sk-proj-", "ghp_", "AKIA")."""
    match = _PREFIX.match(value)
    return match.group(0) if match and len(match.group(0)) < len(value) else ""


def key_words(key: str) -> list[str]:
    """Palavras do nome de um campo: "DB_PASSWORD" -> [db, password]; "clientSecret" -> [client, secret]."""
    return [part.lower() for chunk in re.split(r"[_.\-\s]+", key) for part in _IDENTIFIER_PARTS.findall(chunk)]


def key_kind(key: str) -> str | None:
    """SENHA, SEGREDO ou None conforme o nome do campo."""
    words = key_words(key)
    if not words or any(word in NOT_SECRET_WORDS for word in words):
        return None
    if any(word in PASSWORD_WORDS for word in words):
        return "SENHA"
    if any(word in SECRET_WORDS for word in words):
        return "SEGREDO"
    if any(pair in SECRET_PAIRS for pair in zip(words, words[1:], strict=False)):
        return "SEGREDO"
    return None


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in PLACEHOLDERS
        or value[0] in "$%<{[#*"
        or _FILLER.fullmatch(value) is not None
        or _DOTTED.fullmatch(value) is not None
        or _CONSTANT.fullmatch(value) is not None
        or lowered.startswith(("your", "sua_", "seu_", "<", "example", "exemplo", "process.env", "os.environ"))
    )


def entropy(value: str) -> float:
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def looks_random(value: str) -> bool:
    """Tem cara de chave gerada: um trecho longo misturando letras e números, ou longo e com alta entropia."""
    if len(value) < 8 or is_placeholder(value):
        return False
    for run in _RANDOM_RUN.findall(value):
        has_digit = any(char.isdigit() for char in run)
        has_letter = any(char.isalpha() for char in run)
        if has_digit and has_letter:
            return True
        if len(run) >= 24 and any(c.isupper() for c in run) and any(c.islower() for c in run) and entropy(run) >= 3.5:
            return True
    return False


def plausible_password(value: str, prose: bool) -> bool:
    if len(value) < 4 or is_placeholder(value):
        return False
    # Na prosa, uma palavra comum não é senha: "a senha é forte", "Senha: deve conter 8 caracteres".
    return not (prose and value.isalpha() and (value.islower() or value[1:].islower()))


class SecretRecognizer:
    """Acha chaves de API, tokens, senhas, chaves privadas e URLs de conexão com senha."""

    name = "segredos"
    labels = frozenset(LABELS)

    def __init__(self, rules: Iterable[SecretRule] | None = None):
        self.rules = tuple(load_rules() if rules is None else rules)

    def find(self, text: str) -> Iterable[Candidate]:
        for rule in self.rules:
            for match in rule.pattern.finditer(text):
                start, end = match.span(rule.group)
                value = text[start:end].rstrip(rule.trim) if rule.trim else text[start:end]
                end = start + len(value)
                if not value or (rule.filter == "aleatorio" and not looks_random(value)):
                    continue
                yield Candidate(rule.label, start, end, rule.score, self.name)
        for match in ASSIGNMENT.finditer(text):
            kind = key_kind(match.group(1))
            if kind is None:
                continue
            value = match.group(3)
            if text[match.end(3):match.end(3) + 1] == "(":
                continue  # password = getpass()
            if kind == "SENHA":
                # "Senha: deve conter 8 caracteres" é prosa; "DB_PASSWORD=..." e "password = ..." são configuração.
                prose = match.group(2) == ":" and len(key_words(match.group(1))) == 1
                if plausible_password(value, prose=prose):
                    yield Candidate("SENHA", match.start(3), match.end(3), 0.85, self.name)
            elif looks_random(value):
                yield Candidate("SEGREDO", match.start(3), match.end(3), 0.85, self.name)
        for match in PROSE_PASSWORD.finditer(text):
            if plausible_password(match.group(2), prose=True):
                yield Candidate("SENHA", match.start(2), match.end(2), 0.8, self.name)
