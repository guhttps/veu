"""Detectores por padrão: documentos, contatos e números brasileiros."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from veu import validators as v
from veu._text import fold, words_regex
from veu.recognizers.base import Candidate, context_window

# Limites que impedem casar no meio de um número ou palavra maior.
B = r"(?<![\w])"
E = r"(?![\w])"


@dataclass(frozen=True)
class Scores:
    """Pontuação conforme o valor é válido (dígitos verificadores) e se há contexto por perto.

    None descarta o candidato naquela situação. Sem os campos de contexto, o contexto soma 0,15.
    """

    valid: float | None
    invalid: float | None = None
    valid_context: float | None = None
    invalid_context: float | None = None

    def pick(self, is_valid: bool, has_context: bool) -> float | None:
        if is_valid:
            base, with_context = self.valid, self.valid_context
        else:
            base, with_context = self.invalid, self.invalid_context
        if not has_context:
            return base
        if with_context is not None:
            return with_context
        return None if base is None else min(1.0, base + 0.15)


@dataclass
class PatternSpec:
    label: str
    pattern: str
    scores: Scores
    validator: Callable[[str], bool] | None = None
    context: tuple[str, ...] = ()
    flags: int = 0
    before: int = 40
    after: int = 20
    # Ajuste final da pontuação (por exemplo, telefone com ou sem separadores).
    adjust: Callable[[str, float], float | None] | None = None
    exclude: Callable[[str], bool] | None = None
    name: str = ""
    compiled: re.Pattern = field(init=False, repr=False)
    context_regex: re.Pattern | None = field(init=False, repr=False)

    def __post_init__(self):
        self.compiled = re.compile(self.pattern, self.flags)
        self.context_regex = words_regex(self.context)


CTX_CPF = ("cpf", "c.p.f", "cadastro de pessoa fisica", "contribuinte", "cpf/cnpj")
CTX_CNPJ = ("cnpj", "c.n.p.j", "cpf/cnpj", "razao social", "inscricao")
CTX_RG = ("rg", "r.g", "identidade", "registro geral", "carteira de identidade", "ssp", "doc. identidade", "cin")
CTX_CNH = ("cnh", "habilitacao", "carteira de motorista", "carteira nacional de habilitacao", "registro da cnh")
CTX_TITULO = ("titulo de eleitor", "titulo eleitoral", "eleitor", "inscricao eleitoral")
CTX_PIS = ("pis", "pasep", "pis/pasep", "nit", "nis", "pis/nit")
CTX_CNS = ("cns", "cartao sus", "cartao do sus", "cartao nacional de saude", "sus")
CTX_RENAVAM = ("renavam",)
CTX_PASSAPORTE = ("passaporte", "passport")
CTX_PHONE = (
    "tel", "tel.", "telefone", "telefones", "celular", "cel", "cel.", "whatsapp", "whats", "zap", "wpp",
    "contato", "fone", "ligar", "ligue", "ramal", "numero",
)
CTX_CEP = ("cep",)
CTX_PLATE = ("placa", "veiculo", "carro", "moto", "caminhao", "automovel")
CTX_CARD = ("cartao", "credito", "debito", "visa", "mastercard", "master", "elo", "amex", "hipercard", "final")
CTX_PIX = ("pix", "chave pix", "chave aleatoria", "chave")
CTX_IP = ("ip", "endereco ip", "ipv4", "ipv6", "acesso", "login")
CTX_BIRTH = (
    "nascimento", "nasc", "nasc.", "nascido", "nascida", "nasceu", "data de nascimento", "dn", "d.n",
    "aniversario", "nascida em", "nascido em",
)
CTX_ACCOUNT = ("conta", "conta corrente", "conta-corrente", "c/c", "cc", "agencia", "ag", "ag.", "poupanca", "conta poupanca")
CTX_PROCESS = ("processo", "autos", "proc", "proc.", "acao", "numero do processo")
CTX_EMAIL = ("email", "e-mail")


def _phone_adjust(value: str, score: float) -> float | None:
    formatted = bool(re.search(r"[()\s.+-]", value))
    return score if formatted else score - 0.3


def _is_year(value: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}", value))


_MONTHS = "janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"

DEFAULT_SPECS: list[PatternSpec] = [
    # CPF
    PatternSpec("CPF", B + r"\d{3}\.\d{3}\.\d{3}-\d{2}" + E, Scores(0.95, 0.5, 1.0, 0.7), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{9}-\d{2}" + E, Scores(0.9, 0.4, 1.0, 0.65), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{3}\s\d{3}\s\d{3}\s\d{2}" + E, Scores(0.85, None, 0.95, 0.6), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{11}" + E, Scores(0.75, None, 0.95, 0.6), v.is_valid_cpf, CTX_CPF),
    # CNPJ (numérico e alfanumérico)
    PatternSpec(
        "CNPJ", B + r"[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}" + E,
        Scores(0.95, 0.5, 1.0, 0.7), v.is_valid_cnpj, CTX_CNPJ,
    ),
    PatternSpec("CNPJ", B + r"\d{14}" + E, Scores(0.75, None, 0.95, 0.6), v.is_valid_cnpj, CTX_CNPJ),
    PatternSpec(
        "CNPJ", B + r"(?=[0-9A-Z]{12}\d{2}" + E + r")(?=[0-9]*[A-Z])[0-9A-Z]{12}\d{2}" + E,
        Scores(0.6, None, 0.95, 0.55), v.is_valid_cnpj, CTX_CNPJ,
    ),
    # Documentos que dependem de contexto: os formatos se confundem com outros números.
    PatternSpec("PIS", B + r"\d{3}\.\d{5}\.\d{2}-\d" + E, Scores(0.85, 0.45, 1.0, 0.75), v.is_valid_pis, CTX_PIS),
    PatternSpec("PIS", B + r"\d{11}" + E, Scores(None, None, 0.97, 0.65), v.is_valid_pis, CTX_PIS, before=25),
    PatternSpec("CNH", B + r"\d{11}" + E, Scores(None, None, 0.97, 0.75), v.is_valid_cnh, CTX_CNH, before=30),
    PatternSpec(
        "TITULO_ELEITOR", B + r"\d{4}\s?\d{4}\s?\d{4}" + E, Scores(None, None, 0.95, 0.75),
        v.is_valid_titulo_eleitor, CTX_TITULO, before=30,
    ),
    PatternSpec(
        "RENAVAM", B + r"\d{9,11}" + E, Scores(None, None, 0.97, 0.75), v.is_valid_renavam, CTX_RENAVAM, before=25,
    ),
    PatternSpec(
        "CNS", B + r"[12789]\d{2}\s?\d{4}\s?\d{4}\s?\d{4}" + E, Scores(0.6, None, 0.97, 0.65), v.is_valid_cns, CTX_CNS,
    ),
    PatternSpec("RG", B + r"\d{1,2}\.\d{3}\.\d{3}-[\dXx]" + E, Scores(0.6, None, 0.95), None, CTX_RG),
    PatternSpec("RG", B + r"\d{7,9}-?[\dXx]?" + E, Scores(None, None, 0.85), None, CTX_RG, before=20),
    PatternSpec("RG", B + r"[A-Z]{2}-?\d{1,2}\.?\d{3}\.?\d{3}" + E, Scores(None, None, 0.85), None, CTX_RG, before=20),
    PatternSpec("PASSAPORTE", B + r"[A-Z]{2}\d{6}" + E, Scores(None, None, 0.9), None, CTX_PASSAPORTE, before=30),
    # Contatos
    PatternSpec(
        "EMAIL", r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w])",
        Scores(0.95), None, CTX_EMAIL,
    ),
    PatternSpec(
        "TELEFONE",
        r"(?<![\w+])(?:\+?55[\s.-]?)?(?:\(\d{2}\)|\d{2})[\s.-]?(?:9[\s.]?\d{4}|[2-5]\d{3})[\s.-]?\d{4}" + E,
        Scores(0.85, None, 0.95), v.is_valid_phone, CTX_PHONE, adjust=_phone_adjust,
    ),
    PatternSpec("TELEFONE", B + r"9\d{4}-\d{4}" + E, Scores(0.7, None, 0.9), None, CTX_PHONE),
    PatternSpec("TELEFONE", B + r"[2-5]\d{3}-\d{4}" + E, Scores(None, None, 0.8), None, CTX_PHONE, before=25),
    # Localização e veículos
    PatternSpec("CEP", B + r"\d{5}-\d{3}" + E, Scores(0.75, None, 0.95), None, CTX_CEP),
    PatternSpec("CEP", B + r"\d{2}\.\d{3}-\d{3}" + E, Scores(0.8, None, 0.95), None, CTX_CEP),
    PatternSpec("CEP", B + r"\d{8}" + E, Scores(None, None, 0.85), None, CTX_CEP, before=15),
    PatternSpec("PLACA", B + r"[A-Z]{3}-\d{4}" + E, Scores(0.8, None, 0.95), None, CTX_PLATE),
    PatternSpec("PLACA", B + r"[A-Z]{3}\d[A-Z]\d{2}" + E, Scores(0.75, None, 0.95), None, CTX_PLATE),
    PatternSpec("PLACA", B + r"[A-Z]{3}\d{4}" + E, Scores(0.45, None, 0.9), None, CTX_PLATE),
    # Financeiro
    PatternSpec(
        "CARTAO_CREDITO", B + r"\d(?:[ -]?\d){12,18}" + E, Scores(0.85, None, 0.95, 0.6), v.is_valid_card, CTX_CARD,
    ),
    PatternSpec(
        "CHAVE_PIX",
        B + r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" + E,
        Scores(None, None, 0.9), None, CTX_PIX,
    ),
    PatternSpec(
        "CONTA_BANCARIA", B + r"\d{1,12}(?:[.-]?\d{1,4})?-[\dXx]" + E, Scores(None, None, 0.85), None, CTX_ACCOUNT,
        before=20, after=0,
    ),
    PatternSpec(
        "CONTA_BANCARIA", B + r"\d{4,12}" + E, Scores(None, None, 0.8), None, CTX_ACCOUNT, before=15, after=0,
        exclude=_is_year,
    ),
    # Rede
    PatternSpec("IP", B + r"(?:\d{1,3}\.){3}\d{1,3}" + E, Scores(0.7, None, 0.9), v.is_valid_ipv4, CTX_IP),
    PatternSpec(
        "IP", r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])", Scores(0.75, None, 0.9),
        v.is_valid_ipv6, CTX_IP,
    ),
    # Datas de nascimento (só com contexto: datas em geral não são dados pessoais)
    PatternSpec(
        "DATA_NASCIMENTO", B + r"(?:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2})" + E,
        Scores(None, None, 0.85), v.is_plausible_birthdate, CTX_BIRTH, before=35, after=0,
    ),
    PatternSpec(
        "DATA_NASCIMENTO", B + rf"\d{{1,2}}\s+de\s+(?:{_MONTHS})\s+de\s+\d{{4}}" + E, Scores(None, None, 0.85),
        v.is_plausible_birthdate, CTX_BIRTH, flags=re.IGNORECASE, before=35, after=0,
    ),
    # Processos judiciais
    PatternSpec(
        "PROCESSO", B + r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}" + E, Scores(0.9, 0.6, 1.0, 0.75),
        v.is_valid_processo_cnj, CTX_PROCESS,
    ),
]


class PatternRecognizer:
    """Acha dados pessoais por expressões regulares, valida e pontua pelo contexto."""

    name = "padroes"

    def __init__(self, specs: Iterable[PatternSpec] | None = None):
        self.specs = list(DEFAULT_SPECS if specs is None else specs)
        self.labels = frozenset(spec.label for spec in self.specs)

    def find(self, text: str) -> Iterable[Candidate]:
        for spec in self.specs:
            for match in spec.compiled.finditer(text):
                value = match.group(0)
                if spec.exclude and spec.exclude(value):
                    continue
                is_valid = spec.validator(value) if spec.validator else True
                has_context = False
                if spec.context_regex is not None:
                    window = context_window(text, match.start(), match.end(), spec.before, spec.after)
                    has_context = spec.context_regex.search(window) is not None
                score = spec.scores.pick(is_valid, has_context)
                if score is not None and spec.adjust:
                    score = spec.adjust(value, score)
                if score is None or score <= 0:
                    continue
                yield Candidate(spec.label, match.start(), match.end(), round(score, 3), spec.name or self.name)


def custom_spec(label: str, pattern: str, score: float = 0.9, context: Iterable[str] = (),
                requires_context: bool = False) -> PatternSpec:
    """Padrão definido pelo usuário (seção [[deteccao.personalizados]] do veu.toml)."""
    words = tuple(fold(word) for word in context)
    scores = Scores(None, None, score) if requires_context else Scores(score, None, min(1.0, score + 0.1))
    return PatternSpec(label.upper(), pattern, scores, None, words, name="personalizado")
