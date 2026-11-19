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

from veu.recognizers.base import Candidate, load_wordlist
from veu.validators import is_valid_bip39

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
# Prosa: "a senha é Gato2024", "senha do wifi: casa1234", "resetei a senha para Tmp#4821", "password to ...".
PROSE_PASSWORD = re.compile(
    r"(?<![A-Za-z0-9])(?:senha|password|passwd)(?:[^\n:=]{0,25}?)"
    r"(\s*(?::|=)\s*|\s+(?:é|eh|is|fica|ficou|era|para|pra|to)\s+)[\"']?("
    + VALUE_CHARS + r"{3,200})",
    re.IGNORECASE,
)

# Sem separador ("Login admin, senha bGsE$34", "rede Visitantes, senha Visit@2026"): só vale com cara de senha.
PROSE_PASSWORD_BARE = re.compile(
    r"(?<![A-Za-z0-9])(?:senha|password|passwd)[ \t]+[\"']?(" + VALUE_CHARS + r"{6,200})", re.IGNORECASE
)
# Cabeçalho Cookie: o valor de um cookie de sessão é uma credencial ("Cookie: session_id=9f2c...; theme=dark").
COOKIE_HEADER = re.compile(r"^[ \t]*(?:set-)?cookie[ \t]*:[ \t]*([^\n]+)", re.IGNORECASE | re.MULTILINE)
COOKIE_PAIR = re.compile(r"([A-Za-z0-9_.-]{1,60})=([^;\s]{8,4096})")
SESSION_COOKIE_WORDS = frozenset({"session", "sessionid", "sess", "sessid", "sid", "phpsessid", "jsessionid", "auth",
                                  "jwt", "remember"})

PASSWORD_WORDS = frozenset({"password", "passwd", "passphrase", "pwd", "senha", "pass", "passw"})
SECRET_WORDS = frozenset({"secret", "token", "apikey", "credential", "credentials", "credencial", "credenciais",
                          "signature", "sig", "auth"})
# Código de verificação por SMS ou app ("seu código de verificação é 483920", "OTP: 1234").
OTP_CODE = re.compile(
    r"(?<![A-Za-z0-9])(?:c[óo]digo\s+(?:de\s+)?(?:verifica[çc][ãa]o|confirma[çc][ãa]o|acesso|autentica[çc][ãa]o|login"
    r"|ativa[çc][ãa]o|valida[çc][ãa]o)|verification\s+code|one[- ]time\s+(?:password|code)|otp|2fa|token\s+sms)"
    r"[^\d\n]{0,25}?(?<!\d)(\d{4,8})(?!\d)",
    re.IGNORECASE,
)
# Senha ou PIN só de números sem separador ("senha do banco 739201", "PIN do cartão 4821"). Um ano solto depois
# de "senha" ("a senha expira em 2027") fica, a não ser que a palavra seja PIN.
NUMERIC_PIN = re.compile(
    r"(?<![A-Za-z0-9])(senha|pin|passcode)(?![A-Za-z])[^\d\n]{0,25}?(?<!\d)(\d{4,8})(?!\d|[.,/:-]\d)", re.IGNORECASE
)
# Frase de recuperação de carteira (BIP-39): 12 a 24 palavras da lista, separadas por espaço, vírgula ou numeração.
SEED_WORD = re.compile(r"[A-Za-z]+")
SEED_GAP = re.compile(r"[ \t\r\n,;]*(?:\d{1,2}[ \t]*[.):-]?[ \t]*)?")
SEED_CONTEXT = re.compile(
    r"seed|semente|mnem[oô]nic|recupera[cç][aã]o|recovery|frase|phrase|palavras|words|carteira|wallet|backup",
    re.IGNORECASE,
)
SEED_SIZES = (24, 21, 18, 15, 12)
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


def looks_like_password(value: str) -> bool:
    """Mistura de letras e números, ou símbolo com letras ou números: "Visit@2026" sim, "inválida" e "123456" não."""
    digit = any(char.isdigit() for char in value)
    alpha = any(char.isalpha() for char in value)
    symbol = any(char in "@#$%!&*?+=_" for char in value)
    return (digit and alpha) or (symbol and (digit or alpha))


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
        position = 0
        while (match := ASSIGNMENT.search(text, position)) is not None:
            # O valor pode trazer outras atribuições: em "https://site/reset?token=8f3a...", a primeira é "https:".
            position = match.end(2)
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
                    position = match.end(3)
            elif looks_random(value):
                yield Candidate("SEGREDO", match.start(3), match.end(3), 0.85, self.name)
                position = match.end(3)
        for match in OTP_CODE.finditer(text):
            yield Candidate("SENHA", match.start(1), match.end(1), 0.8, self.name)
        for match in NUMERIC_PIN.finditer(text):
            digits = match.group(2)
            if len(digits) == 4 and 1950 <= int(digits) <= 2099 and match.group(1).lower() != "pin":
                continue
            yield Candidate("SENHA", match.start(2), match.end(2), 0.75, self.name)
        yield from self._seed_phrases(text)
        for match in PROSE_PASSWORD.finditer(text):
            start, end = match.span(2)
            # O ponto que fecha a frase não faz parte da senha: "resetei a senha para Tmp#4821."
            if match.group(2).endswith(".") and (end == len(text) or text[end].isspace()):
                end -= 1
            if plausible_password(text[start:end], prose=True):
                yield Candidate("SENHA", start, end, 0.8, self.name)
        for match in PROSE_PASSWORD_BARE.finditer(text):
            start, end = match.span(1)
            if match.group(1).endswith(".") and (end == len(text) or text[end].isspace()):
                end -= 1
            value = text[start:end]
            if plausible_password(value, prose=True) and looks_like_password(value):
                yield Candidate("SENHA", start, end, 0.75, self.name)
        for header in COOKIE_HEADER.finditer(text):
            offset = header.start(1)
            for pair in COOKIE_PAIR.finditer(header.group(1)):
                name, value = pair.group(1), pair.group(2)
                words = set(key_words(name))
                if (key_kind(name) or words & SESSION_COOKIE_WORDS) and (looks_random(value) or len(value) >= 16):
                    yield Candidate("SEGREDO", offset + pair.start(2), offset + pair.end(2), 0.85, self.name)

    def _seed_phrases(self, text: str) -> Iterable[Candidate]:
        """Sequências de palavras do BIP-39: com o checksum certo, ou 12+ palavras depois de "seed", "carteira"..."""
        indexes = bip39_indexes()
        run: list[tuple[int, int, int]] = []
        for match in SEED_WORD.finditer(text):
            index = indexes.get(match.group(0).lower())
            if index is not None and run and (match.start() - run[-1][1] > 12
                                              or SEED_GAP.fullmatch(text, run[-1][1], match.start()) is None):
                yield from self._seed_run(text, run)
                run = []
            if index is None:
                yield from self._seed_run(text, run)
                run = []
            else:
                run.append((match.start(), match.end(), index))
        yield from self._seed_run(text, run)

    def _seed_run(self, text: str, run: list[tuple[int, int, int]]) -> Iterable[Candidate]:
        if len(run) < 12:
            return
        for size in SEED_SIZES:  # a maior janela com o checksum certo
            for offset in range(len(run) - size + 1):
                window = run[offset:offset + size]
                if is_valid_bip39([index for _, _, index in window]):
                    yield Candidate("CHAVE_PRIVADA", window[0][0], window[-1][1], 0.99, self.name)
                    return
        start = run[0][0]
        if SEED_CONTEXT.search(text, max(0, start - 80), start):
            yield Candidate("CHAVE_PRIVADA", start, run[-1][1], 0.9, self.name)


@cache
def bip39_indexes() -> dict[str, int]:
    return {word: index for index, word in enumerate(load_wordlist("bip39.txt"))}
