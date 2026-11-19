"""Detectores por padrão: documentos, contatos e números brasileiros, além de IBAN e telefones internacionais."""

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

_CLASS = r"\[(?:\\.|[^\]\\])+\]"
_LEADING = re.compile(rf"\(\?<!({_CLASS})\)(\\[dw]|{_CLASS}|[A-Za-z0-9])(?:\{{(\d+)(?:(,)(\d*))?\}}|(\+))?")


def _class_first(pattern: str) -> str:
    r"""Começa a expressão pela classe de caracteres, e não pelo limite B, quando dá.

    O motor de regex do Python só pula depressa para as posições candidatas quando a expressão começa por uma
    classe; com B na frente, ele tenta o padrão inteiro em cada posição do texto. B + "\d{3}" vira
    "\d(?<![\w]\d)\d{2}", que casa exatamente as mesmas coisas, cerca de 40% mais rápido.
    """
    match = _LEADING.match(pattern)
    if not match:
        return pattern
    before, token, low, comma, high, plus = match.groups()
    # Token opcional ("?", "*", "{0,n}") ou quantificador possessivo: a expressão pode começar depois dele.
    if (low is not None and int(low) == 0) or pattern[match.end():match.end() + 1] in ("?", "*", "+"):
        return pattern
    rest = ""
    if plus:
        rest = token + "*"
    elif low is not None:
        n = int(low) - 1
        if comma:
            rest = token + "{" + str(n) + "," + (str(int(high) - 1) if high else "") + "}"
        elif n:
            rest = token + ("{" + str(n) + "}" if n > 1 else "")
    return token + "(?<!" + before + token + ")" + rest + pattern[match.end():]


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
    # Sem contexto, descarta pelo que está em volta no texto (text, start, end): "exp":1735689600 não é telefone.
    exclude_at: Callable[[str, int, int], bool] | None = None
    name: str = ""
    compiled: re.Pattern = field(init=False, repr=False)
    context_regex: re.Pattern | None = field(init=False, repr=False)

    def __post_init__(self):
        self.compiled = re.compile(_class_first(self.pattern), self.flags)
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
CTX_CTPS = ("ctps", "c.t.p.s", "carteira de trabalho", "carteira profissional")
_UFS = r"(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"
CTX_PHONE = (
    "tel", "tel.", "telefone", "telefones", "celular", "cel", "cel.", "whatsapp", "whats", "zap", "wpp",
    "contato", "fone", "ligar", "ligue", "ramal", "numero", "phone", "mobile", "cellphone",
    "cell", "call", "movil", "telefono", "telephone", "portable", "handy", "telefon", "cellulare", "telemovel", "tlm",
)
# Endereços e códigos postais de outros países (Espanha e América Latina, França, Alemanha, Estados Unidos).
_LETTER = "A-Za-zÀ-ÖØ-öø-ÿ"
_ES_STREET = (r"(?<![\w])(?:Calle|C/|Avenida|Avda\.?|Plaza|Pza\.?|Paseo|Carrera|Cra\.?|Carretera|Camino|Ronda|Glorieta)"
              r"\s+(?:(?:de|del|la|las|los|el)\s+)*[A-ZÀ-Ý][" + _LETTER + r"]+(?:\s+(?:(?:de|del|la|las|los|el|y)\s+)*"
              r"[A-ZÀ-Ý][" + _LETTER + r"]+){0,3},?\s+(?:n[ºo°]\.?\s*|#\s*)?\d{1,5}[A-Za-z]?(?![\w])")
_FR_STREET = (r"(?<![\w])\d{1,4}(?:\s?(?:bis|ter))?,?\s+(?:[Rr]ue|[Aa]venue|[Bb]oulevard|[Bb]d|[Pp]lace|[Cc]hemin|"
              r"[Aa]llée|[Ii]mpasse|[Qq]uai|[Rr]oute|[Cc]ours)\s+(?:(?:de|du|des|la|le)\s+|l'|d')*[A-ZÀ-Ý]["
              + _LETTER + r"'-]+(?:\s+(?:(?:de|du|des|la|le)\s+|l'|d')*[A-ZÀ-Ý][" + _LETTER + r"'-]+){0,3}")
_DE_STREET = (r"(?<![\w])(?:[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)*(?:straße|strasse|str\.|weg|platz|allee|gasse|"
              r"ring|damm|ufer)|[A-ZÄÖÜ][a-zäöüß]+\s+(?:Straße|Strasse|Str\.|Weg|Platz|Allee|Gasse|Ring|Damm|Ufer))"
              r"\s+\d{1,4}[a-z]?(?![\w])")
_EN_STREET = (r"(?<![\w])\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:Street|St\.|St|Avenue|Ave\.?|"
              r"Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Terrace|Way|Place|Pl\.?|Parkway|Pkwy\.?|"
              r"Circle|Cir\.?|Highway|Hwy\.?)(?![\w])(?:,?\s+(?:Apt|Suite|Unit|#)\.?\s*[\w-]+)?")
_US_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|"
              "OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC")
CTX_CEP = ("cep",)
CTX_PLATE = ("placa", "veiculo", "carro", "moto", "caminhao", "automovel")
CTX_CARD = ("cartao", "credito", "debito", "visa", "mastercard", "master", "elo", "amex", "hipercard", "final")
CTX_PIX = ("pix", "chave pix", "chave aleatoria", "chave")
CTX_IP = ("ip", "endereco ip", "ipv4", "ipv6", "acesso", "login")
CTX_BIRTH = (
    "nascimento", "nasc", "nasc.", "nascido", "nascida", "nasceu", "data de nascimento", "dn", "d.n",
    "aniversario", "nascida em", "nascido em", "birth", "birth date", "birthdate", "date of birth", "dob", "born",
    "ne le", "nee le", "date de naissance", "geboren am", "geboren", "geb.", "geburtsdatum", "nacido el",
    "nacida el", "fecha de nacimiento", "nato il", "nata il", "data di nascita",
)
# Nomes de coluna: em tabelas (SQL, CSV, JSON), o cabeçalho "nascimento" fica longe do valor.
CTX_BIRTH_COLUMN = (
    "nascimento", "data_nascimento", "dt_nascimento", "datanascimento", "data_nasc", "dt_nasc", "nasc",
    "birth_date", "birthdate", "date_of_birth", "dob", "data de nascimento", "data nascimento",
)
CTX_MAC = ("mac", "endereco mac", "mac address", "macaddress", "hwaddr", "ether", "bssid")
CTX_COORD = (
    "coordenadas", "coordenada", "localizacao", "local", "gps", "lat", "latitude", "lng", "lon", "longitude",
    "geolocalizacao", "posicao", "location",
)
CTX_IMEI = ("imei", "imei1", "imei 1", "imei2", "imei 2")
CTX_BOLETO = ("boleto", "linha digitavel", "codigo de barras", "fatura", "pagamento", "pagar", "conta", "vencimento")
CTX_CERTIDAO = ("certidao", "matricula", "registro civil", "nascimento", "casamento", "obito", "cartorio", "registro")
# E-mail disfarçado ("joao.silva [at] gmail [dot] com", "maria arroba gmail ponto com").
_OBF_AT = r"\s*[\[({<]\s*(?:at|arroba)\s*[\])}>]\s*"
_OBF_DOT = r"(?:\s*[\[({<]\s*(?:dot|ponto)\s*[\])}>]\s*|\s+(?:dot|ponto)\s+)"
_EMAIL_TLDS = (r"(?:com|net|org|br|gov|edu|io|me|co|info|biz|dev|app|pt|us|uk|es|ar|mx|cl|uy|py|de|fr|it|jus|mil|adv"
               r"|ind|tech|online|site)")
# Coordenadas em graus, minutos e (opcional) segundos: 23°33'01"S 46°38'02"W.
_DMS = r"\d{1,3}\s*°\s*\d{1,2}(?:[.,]\d+)?\s*['′’]\s*(?:\d{1,2}(?:[.,]\d+)?\s*(?:\"|″|”|''|′′)\s*)?"
# Números de cadastro em instituições: prontuário, matrícula (RA), carteirinha do convênio, apólice.
CTX_CADASTRO = (
    "prontuario", "carteirinha", "carteira do convenio", "carteira do plano", "cartao do convenio",
    "cartao do plano", "numero da carteira", "matricula", "ra", "registro academico", "apolice",
    "codigo do beneficiario", "numero do beneficiario", "nb", "numero do beneficio", "beneficio do inss",
    "beneficio inss",
)
CTX_ACCOUNT = ("conta", "conta corrente", "conta-corrente", "c/c", "cc", "agencia", "ag", "ag.", "poupanca", "conta poupanca")
CTX_PROCESS = ("processo", "autos", "proc", "proc.", "acao", "numero do processo")
CTX_EMAIL = ("email", "e-mail")
CTX_IBAN = ("iban", "swift", "bic", "transferencia internacional", "conta internacional")
# Outros países (pt-PT e espanhol, sem acento: o contexto é comparado depois do fold).
CTX_NIF_PT = ("nif", "nipc", "contribuinte", "n.o de contribuinte", "numero de identificacao fiscal",
              "pessoa coletiva", "pessoa colectiva")
CTX_CC_PT = ("cartao de cidadao", "cc", "n.o do documento", "nic", "bilhete de identidade", "bi")
CTX_NISS_PT = ("niss", "seguranca social", "n.o de beneficiario")
CTX_CUIT = ("cuit", "cuil", "afip", "arca", "clave fiscal")
CTX_DNI = ("dni", "d.n.i", "documento nacional de identidad", "reniec")
CTX_MX = ("curp", "rfc", "homoclave", "sat", "registro federal de contribuyentes")
CTX_RUT = ("rut", "run", "rol unico", "rol unico tributario", "sii", "dgi")
CTX_CEDULA = ("cedula", "c.i", "ci", "c.c", "cedula de ciudadania", "cedula de identidad", "documento de identidad",
              "carnet de identidad")
CTX_NIT = ("nit", "dian")
CTX_RUC = ("ruc", "sunat", "sri", "set", "registro unico de contribuyentes")
CTX_RIF = ("rif", "seniat")
_CUIT_PREFIX = "(?:20|23|24|27|30|33|34|50|51|55)"
CTX_NUIT = ("nuit", "autoridade tributaria", "numero unico de identificacao tributaria")
CTX_BI_AFRICA = ("bi", "bilhete de identidade", "nif", "agt", "nuit")
CTX_SSN = ("ssn", "social security", "soc sec", "itin", "taxpayer identification", "tin")
CTX_MBI = ("mbi", "medicare", "beneficiary")
CTX_DNI_ES = ("dni", "nie", "nif", "documento nacional de identidad")
CTX_CF = ("codice fiscale", "c.f", "cod. fisc", "tessera sanitaria")
CTX_NIR = ("nir", "insee", "securite sociale", "n° ss", "carte vitale")
CTX_STEUER = ("steuer-id", "steuerid", "steueridentifikationsnummer", "idnr", "identifikationsnummer")
CTX_NINO = ("national insurance", "ni number", "nino")
CTX_NHS = ("nhs", "nhs number")
CTX_BSN = ("bsn", "burgerservicenummer", "sofinummer")
CTX_SIN = ("sin", "social insurance number", "numero d'assurance sociale")
CTX_AADHAAR = ("aadhaar", "uidai", "uid number")
CTX_PAN = ("pan", "permanent account number", "income tax")
CTX_MRZ = ("passaporte", "passport", "mrz")
CTX_VIN = ("chassi", "chassis", "vin", "numero do chassi")
CTX_HOST = ("servidor", "server", "host", "hostname", "banco", "database", "conectar", "conexao", "endpoint", "porta",
            "port", "ssh", "redis", "postgres", "mysql", "api")
CTX_SHELL = ("ssh", "scp", "sftp", "psql", "mysql", "telnet", "nc", "docker", "redis-cli", "mongosh")
# Terminações de nomes que só existem dentro de uma rede (RFC 6762, RFC 8375 e os costumes de redes de empresas).
_INTERNAL_TLDS = r"(?:local|localdomain|internal|interna|interno|lan|corp|intranet|home\.arpa)"
CTX_CRYPTO = ("carteira", "wallet", "bitcoin", "btc", "ethereum", "eth", "cripto", "usdt", "tron", "trc20", "litecoin",
              "ltc", "dogecoin", "doge")
CTX_PRIVATE_KEY = ("chave privada", "private key", "privkey", "priv key", "secret key", "chave secreta", "private_key")


def _mrz_name_line(value: str) -> bool:
    """1ª linha da MRZ: "P<" + país + sobrenome<<nomes, completando com "<"."""
    return "<<" in value[5:] and any(char.isalpha() for char in value[5:])


# Horário Unix (2001 a 2033: 10 dígitos começando com 1) colado a uma chave ("exp":, ts=) ou a "timestamp".
_TIMESTAMP_BEFORE = re.compile(
    r"(?:[=:][ \t]*[\"']?|\b(?:timestamp|epoch|unix|ts|exp|iat|nbf|time|created|updated|expires)[\"' \t:=]*)$",
    re.IGNORECASE,
)


def _looks_like_timestamp(text: str, start: int, end: int) -> bool:
    value = text[start:end]
    return (len(value) == 10 and value.isdigit() and value[0] == "1"
            and _TIMESTAMP_BEFORE.search(text[max(0, start - 16):start]) is not None)


def _phone_adjust(value: str, score: float) -> float | None:
    formatted = bool(re.search(r"[()\s.+-]", value))
    return score if formatted else score - 0.3


# Documentos já mascarados pela metade ("324.327.***-**", "***.982.247-**"): os dígitos que sobram ainda
# identificam a pessoa. Só valem com pelo menos 3 dígitos à mostra.
M = r"[\d*xX\u2022]"


def _partially_masked(value: str) -> bool:
    return sum(char.isdigit() for char in value) >= 3 and any(char in "*xX\u2022" for char in value)


def _is_year(value: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}", value))


_MONTHS = "janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"

DEFAULT_SPECS: list[PatternSpec] = [
    # CPF
    PatternSpec("CPF", B + r"\d{3}\.\d{3}\.\d{3}-\d{2}" + E, Scores(0.95, 0.5, 1.0, 0.7), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{9}-\d{2}" + E, Scores(0.9, 0.4, 1.0, 0.65), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{3}\s\d{3}\s\d{3}\s\d{2}" + E, Scores(0.85, None, 0.95, 0.6), v.is_valid_cpf, CTX_CPF),
    PatternSpec("CPF", B + r"\d{11}" + E, Scores(0.75, None, 0.95, 0.6), v.is_valid_cpf, CTX_CPF),
    # Disfarces e digitação descuidada: hífens no lugar dos pontos ("529-982-247-25") e um espaço entre cada dígito.
    PatternSpec("CPF", B + r"\d{3}[.\-]\d{3}[.\-]\d{3}[.\-/]\d{2}" + E, Scores(0.85, None, 0.95), v.is_valid_cpf,
                CTX_CPF, name="separadores"),
    PatternSpec("CPF", B + r"\d(?: \d){10}" + E, Scores(None, None, 0.9), v.is_valid_cpf, CTX_CPF, before=20,
                name="espacado"),
    PatternSpec("CPF", rf"(?<![\w*]){M}{{3}}\.{M}{{3}}\.{M}{{3}}-{M}{{2}}(?![\w*])", Scores(0.85, None, 0.97),
                _partially_masked, CTX_CPF, name="mascarado"),
    # CNPJ (numérico e alfanumérico)
    PatternSpec(
        "CNPJ", B + r"[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}" + E,
        Scores(0.95, 0.5, 1.0, 0.7), v.is_valid_cnpj, CTX_CNPJ,
    ),
    PatternSpec("CNPJ", B + r"\d{14}" + E, Scores(0.75, None, 0.95, 0.6), v.is_valid_cnpj, CTX_CNPJ),
    PatternSpec("CNPJ", B + r"\d{2}\s\d{3}\s\d{3}\s\d{4}\s\d{2}" + E, Scores(0.85, None, 0.95, 0.6), v.is_valid_cnpj,
                CTX_CNPJ),
    PatternSpec("CNPJ", rf"(?<![\w*]){M}{{2}}\.{M}{{3}}\.{M}{{3}}/{M}{{4}}-{M}{{2}}(?![\w*])", Scores(0.85, None, 0.97),
                _partially_masked, CTX_CNPJ, name="mascarado"),
    PatternSpec(
        "CNPJ", B + r"(?=[0-9A-Z]{12}\d{2}" + E + r")(?=[0-9]*[A-Z])[0-9A-Z]{12}\d{2}" + E,
        Scores(0.6, None, 0.95, 0.55), v.is_valid_cnpj, CTX_CNPJ,
    ),
    # Documentos que dependem de contexto: os formatos se confundem com outros números.
    PatternSpec("PIS", B + r"\d{3}\.\d{5}\.\d{2}-\d" + E, Scores(0.85, 0.45, 1.0, 0.75), v.is_valid_pis, CTX_PIS),
    PatternSpec("PIS", B + r"\d{11}" + E, Scores(None, None, 0.97, 0.65), v.is_valid_pis, CTX_PIS, before=25),
    PatternSpec("CNH", B + r"\d{11}" + E, Scores(None, None, 0.97, 0.75), v.is_valid_cnh, CTX_CNH, before=30),
    PatternSpec("CNH", B + r"\d{10}-\d" + E, Scores(None, None, 0.97, 0.75), v.is_valid_cnh, CTX_CNH, before=30),
    PatternSpec("CNH", rf"(?<![\w*]){M}{{11}}(?![\w*])", Scores(None, None, 0.9), _partially_masked, CTX_CNH, before=30,
                name="mascarado"),
    PatternSpec(
        "TITULO_ELEITOR", B + r"\d{4}\s?\d{4}\s?\d{4}" + E, Scores(None, None, 0.95, 0.75),
        v.is_valid_titulo_eleitor, CTX_TITULO, before=30,
    ),
    PatternSpec("TITULO_ELEITOR", rf"(?<![\w*]){M}{{4}}\s?{M}{{4}}\s?{M}{{4}}(?![\w*])", Scores(None, None, 0.9),
                _partially_masked, CTX_TITULO, before=30, name="mascarado"),
    PatternSpec(
        "RENAVAM", B + r"\d{9,11}" + E, Scores(None, None, 0.97, 0.75), v.is_valid_renavam, CTX_RENAVAM, before=25,
    ),
    PatternSpec(
        "CNS", B + r"[12789]\d{2}\s?\d{4}\s?\d{4}\s?\d{4}" + E, Scores(0.6, None, 0.97, 0.65), v.is_valid_cns, CTX_CNS,
    ),
    PatternSpec("RG", B + r"\d{1,2}\.\d{3}\.\d{3}-[\dXx]" + E, Scores(0.6, None, 0.95), None, CTX_RG),
    PatternSpec("RG", B + r"\d{7,9}-?[\dXx]?" + E, Scores(None, None, 0.85), None, CTX_RG, before=20),
    PatternSpec("RG", B + r"[A-Z]{2}-?\d{1,2}\.?\d{3}\.?\d{3}" + E, Scores(None, None, 0.85), None, CTX_RG, before=20),
    PatternSpec("RG", B + r"\d{1,2}\s\d{3}\s\d{3}\s[\dXx]" + E, Scores(None, None, 0.85), None, CTX_RG, before=20),
    PatternSpec("RG", rf"(?<![\w*]){M}{{1,2}}\.?{M}{{3}}\.?{M}{{2,3}}-?{M}(?![\w*])", Scores(None, None, 0.85),
                _partially_masked, CTX_RG, before=20, name="mascarado"),
    PatternSpec("PASSAPORTE", B + r"[A-Z]{2}\d{6}" + E, Scores(None, None, 0.9), None, CTX_PASSAPORTE, before=30),
    # Registro em conselho profissional ("OAB/SP 123.456", "CRM-SC nº 12345", "CRP 06/123456"). Só o número some:
    # a sigla e o estado ficam, para a IA saber de que profissional se trata. Sem o estado, "CRM 365" seria software.
    PatternSpec(
        "REGISTRO_PROFISSIONAL",
        r"(?<![\w/])(?:OAB|CRM|CRO|CREA|CRF|CRMV|CRN|COREN|CRC|CREFITO|CREFONO|CRBM|CRESS|CRA)[ \t]?[-/ ][ \t]?" + _UFS
        + r"[ \t]*[,:]?[ \t]*(?:(?:n[º°o]\.?|número)[ \t]*)?(?P<valor>\d{1,3}(?:\.\d{3}){1,2}|\d{3,10})(?![\w])",
        Scores(0.9),
    ),
    PatternSpec("REGISTRO_PROFISSIONAL", r"(?<![\w/])CRP[ \t]?[-/ ]?[ \t]?(?P<valor>\d{2}/\d{3,6})(?![\w])", Scores(0.9)),
    # CTPS antiga, com número e série ("CTPS nº 1234567 série 0012-SP"); a digital usa o CPF.
    PatternSpec("CTPS", B + r"\d{5,8}" + E, Scores(None, None, 0.85), None, CTX_CTPS, before=25),
    PatternSpec(
        "CTPS", r"(?<![\w])s[ée]rie[ \t]*(?:n[º°o]\.?[ \t]*)?(?P<valor>\d{3,5}(?:-?[A-Z]{2})?)(?![\w])",
        Scores(None, None, 0.85), None, CTX_CTPS, flags=re.IGNORECASE, before=40,
    ),
    # Contatos
    PatternSpec(
        "EMAIL", r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w])",
        Scores(0.95), None, CTX_EMAIL,
    ),
    # Codificado em URL ("checkout?email=ana%40example.com"): o %40 é o @.
    PatternSpec(
        # O lookbehind cobre todos os caracteres do usuário (inclusive o %): a busca só começa no início de cada
        # trecho, sem varrer o resto do texto a partir de cada letra ("%40%40..." ficava quadrático).
        "EMAIL", r"(?<![\w.%+-])[A-Za-z0-9._%+-]+" + _OBF_AT + r"[A-Za-z0-9-]+(?:(?:" + _OBF_DOT + r"|\.)[A-Za-z0-9-]+)*"
        r"(?:" + _OBF_DOT + r"|\.)" + _EMAIL_TLDS + r"(?![\w])", Scores(0.9), flags=re.IGNORECASE, name="disfarcado",
    ),
    PatternSpec(
        "EMAIL", r"(?<![\w.%+-])[A-Za-z0-9._%+-]+\s+(?:at|arroba)\s+[A-Za-z0-9-]+(?:" + _OBF_DOT + r"[A-Za-z0-9-]+)*"
        + _OBF_DOT + _EMAIL_TLDS + r"(?![\w])", Scores(0.85), flags=re.IGNORECASE, name="disfarcado",
    ),
    PatternSpec(
        "EMAIL", r"(?<![\w.+-])[A-Za-z0-9._+-]+%40[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w])",
        Scores(0.9), None, CTX_EMAIL, name="url",
    ),
    PatternSpec(
        "TELEFONE",
        r"(?<![\w+])(?:\+?55[\s.-]?)?(?:\(\d{2}\)|\d{2})[\s.-]?(?:9[\s.]?\d{4}|[2-5]\d{3})[\s.-]?\d{4}" + E,
        Scores(0.85, None, 0.95), v.is_valid_phone, CTX_PHONE, adjust=_phone_adjust, exclude_at=_looks_like_timestamp,
    ),
    PatternSpec("TELEFONE", B + r"9\d{4}-\d{4}" + E, Scores(0.7, None, 0.9), None, CTX_PHONE),
    # Estados Unidos e Canadá: "(415) 555-0132".
    PatternSpec("TELEFONE", r"(?<![\w+(])\([2-9]\d{2}\)[ ]?[2-9]\d{2}[-. ]\d{4}" + E, Scores(0.85, None, 0.95), None,
                CTX_PHONE, name="nanp"),
    # Qualquer país, sem o +código, com "tel", "móvil", "telemóvel", "Handy" por perto: "55 1234 5678", "912 345 678".
    PatternSpec("TELEFONE", r"(?<![\w+/.,-])\d{2,5}(?:[ .-]\d{2,8}){1,4}(?![\w]|[.,/-]\d)", Scores(None, None, 0.8),
                v.is_plausible_phone_digits, CTX_PHONE, before=25, name="contexto"),
    # Internacional: +código do país (menos o 55, coberto acima) e grupos de dígitos.
    PatternSpec(
        "TELEFONE", r"(?<![\w+])\+(?!55)[1-9]\d{0,2}(?:[\s.-]?\(?\d{1,4}\)?){1,2}(?:[\s.-]?\d{2,4}){2,4}" + E,
        Scores(0.8, None, 0.95), v.is_valid_intl_phone, CTX_PHONE,
    ),
    PatternSpec("TELEFONE", B + r"[2-5]\d{3}-\d{4}" + E, Scores(None, None, 0.8), None, CTX_PHONE, before=25),
    # Localização e veículos
    PatternSpec("CEP", B + r"\d{5}-\d{3}" + E, Scores(0.75, None, 0.95), None, CTX_CEP),
    PatternSpec("CEP", B + r"\d{2}\.\d{3}-\d{3}" + E, Scores(0.8, None, 0.95), None, CTX_CEP),
    PatternSpec("CEP", B + r"\d{8}" + E, Scores(None, None, 0.85), None, CTX_CEP, before=15),
    PatternSpec("CEP", B + r"\d{5}\s\d{3}" + E, Scores(None, None, 0.85), None, CTX_CEP, before=15),
    # Códigos postais de fora: Portugal ("1100-053 Lisboa"), EUA ("IL 62704") e ", 28013 Madrid" depois do endereço.
    PatternSpec("CEP", B + r"\d{4}-\d{3}(?=[ \t]+[A-ZÀ-Ý])", Scores(0.85), name="exterior"),
    PatternSpec("CEP", r"(?<![\w])(?:" + _US_STATES + r"),?[ \t]+(?P<valor>\d{5}(?:-\d{4})?)" + E, Scores(0.85),
                name="exterior"),
    PatternSpec("CEP", r"(?<=,[ ])\d{5}(?=[ ][A-ZÀ-Ý][a-zà-ÿ]+(?:[ -][A-ZÀ-Ý][a-zà-ÿ]+)?(?:[.,;)\n]|$))", Scores(0.8),
                name="exterior"),
    PatternSpec("ENDERECO", _ES_STREET, Scores(0.85), name="exterior"),
    PatternSpec("ENDERECO", _FR_STREET, Scores(0.85), name="exterior"),
    PatternSpec("ENDERECO", _DE_STREET, Scores(0.85), name="exterior"),
    PatternSpec("ENDERECO", _EN_STREET, Scores(0.85), name="exterior"),
    PatternSpec("PLACA", B + r"[A-Z]{3}-\d{4}" + E, Scores(0.8, None, 0.95), None, CTX_PLATE),
    PatternSpec("PLACA", B + r"[A-Z]{3}\d[A-Z]\d{2}" + E, Scores(0.75, None, 0.95), None, CTX_PLATE),
    PatternSpec("PLACA", B + r"[A-Z]{3}\d{4}" + E, Scores(0.45, None, 0.9), None, CTX_PLATE),
    # Financeiro
    PatternSpec(
        "CARTAO_CREDITO", B + r"\d(?:[ -]?\d){12,18}" + E, Scores(0.85, None, 0.95, 0.6), v.is_valid_card, CTX_CARD,
    ),
    # CVV do cartão: só o número depois de "CVV", "CVC" ou "código de segurança".
    PatternSpec(
        "CARTAO_CREDITO",
        r"(?<![\w])(?:CVV2?|CVC2?|CSC|c[óo]d(?:igo|\.)?\s+de\s+seguran[çc]a)(?:\s+do\s+cart[ãa]o)?[\s:=nº°.-]{0,5}"
        r"(?P<valor>\d{3,4})(?![\w])", Scores(0.9), flags=re.IGNORECASE, name="cvv",
    ),
    # Boleto: linha digitável bancária (47 dígitos), de arrecadação (48, começa com 8) e código de barras (44).
    PatternSpec(
        "BOLETO", B + r"\d{5}\.?\d{5}[ \t]+\d{5}\.?\d{6}[ \t]+\d{5}\.?\d{6}[ \t]+\d[ \t]+\d{14}" + E, Scores(0.95, 0.8),
        v.is_valid_boleto,
    ),
    PatternSpec("BOLETO", B + r"8\d{10}[ -]?\d(?:[ \t]+\d{11}[ -]?\d){3}" + E, Scores(0.95, 0.8), v.is_valid_boleto),
    PatternSpec("BOLETO", B + r"(?:\d{44}|\d{47,48})" + E, Scores(0.9, None, 0.97), v.is_valid_boleto, CTX_BOLETO),
    # Pix copia e cola (BR Code): traz a chave, o nome e a cidade de quem recebe. Duas buscas na linha (até a
    # primeira e até a última terminação "6304" + CRC); só vale com o CRC certo.
    PatternSpec("CHAVE_PIX", r"(?<![\w])000201[^\n]{20,600}?6304[0-9A-Fa-f]{4}(?![0-9A-Fa-f])", Scores(0.99),
                v.is_valid_brcode, name="brcode"),
    PatternSpec("CHAVE_PIX", r"(?<![\w])000201[^\n]{20,600}6304[0-9A-Fa-f]{4}(?![0-9A-Fa-f])", Scores(0.99),
                v.is_valid_brcode, name="brcode"),
    PatternSpec(
        "IBAN", B + r"[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?" + E, Scores(0.95, None, 1.0),
        v.is_valid_iban, CTX_IBAN,
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
    # Em tabelas, só datas dentro de uma célula (depois de aspas, vírgula, ponto e vírgula, barra ou tabulação) e
    # com a coluna "nascimento" no cabeçalho: "INSERT ... (nome, nascimento) VALUES ('Ana', '1985-04-03')".
    PatternSpec(
        "DATA_NASCIMENTO", r"(?<=['\";,|\t])[ ]?(?P<valor>\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})(?![\w])",
        Scores(None, None, 0.8), v.is_plausible_birthdate, CTX_BIRTH_COLUMN, before=600, after=0, name="tabela",
    ),
    # Coordenadas de GPS ("-23.550520, -46.633308"): sem contexto, só com sinal negativo e cinco casas decimais.
    PatternSpec(
        "COORDENADAS",
        r"(?<![\w.-])-?(?:[0-8]?\d|90)\.\d{4,8}[ \t]*,[ \t]*-?(?:1[0-7]\d|0?\d?\d|180)\.\d{4,8}(?![\w]|\.\d)",
        Scores(0.8, None, 0.9, 0.85), v.is_likely_coordinates, CTX_COORD, before=40,
    ),
    PatternSpec("COORDENADAS", r"(?<![\w.])" + _DMS + r"[NSns](?![\w])[\s,;/]{0,4}" + _DMS + r"[LOWElowe](?![\w])",
                Scores(0.9), v.is_valid_dms, name="gms"),
    # Celular: IMEI (15 dígitos com Luhn). Com "IMEI" por perto, vence o cartão de crédito.
    PatternSpec("IMEI", B + r"\d{2}[ -]?\d{6}[ -]?\d{6}[ -]?\d" + E, Scores(0.86, None, 0.97), v.is_valid_imei, CTX_IMEI),
    # Matrícula de certidão do registro civil (nascimento, casamento, óbito): 32 dígitos.
    PatternSpec(
        "CERTIDAO", B + r"\d{6}[ .]?\d{2}[ .]?\d{2}[ .]?\d{4}[ .]?\d[ .]?\d{5}[ .]?\d{3}[ .]?\d{7}[ .-]?\d{2}" + E,
        Scores(0.9, None, 0.97), v.is_likely_certidao, CTX_CERTIDAO,
    ),
    # Registro Nacional Migratório (RNM, antigo RNE) de estrangeiros no Brasil.
    PatternSpec("RG", r"(?<![\w])(?:RNM|RNE|CRNM)(?![\w])[\s:nº°.-]{0,6}(?P<valor>[A-Za-z]\d{6}-?[0-9A-Za-z])(?![\w])",
                Scores(0.9), flags=re.IGNORECASE, name="rnm"),
    # Números de cadastro (prontuário, matrícula, carteirinha, apólice), só com o contexto; datas e valores ficam.
    PatternSpec(
        "CADASTRO", r"(?<![\w.,/$-])(?<!R\$ )\d[\d.\-/]{3,22}\d(?![\w]|,\d)", Scores(None, None, 0.8), None, CTX_CADASTRO,
        before=30, exclude=lambda value: re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}", value)
        is not None,
    ),
    # Processos judiciais
    PatternSpec(
        "PROCESSO", B + r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}" + E, Scores(0.9, 0.6, 1.0, 0.75),
        v.is_valid_processo_cnj, CTX_PROCESS,
    ),
    # Outros países. Três níveis de confiança:
    # - formatos estruturados ou com a pontuação típica: sem contexto (CURP, RFC, CC, CUIT com hífens, RIF);
    # - numéricos de 11 dígitos ou mais, que podem ser CPF: só com contexto, e aí vencem o CPF;
    # - numéricos curtos, que qualquer número de 7 a 9 dígitos pode imitar: só com contexto.
    # A versão do cartão são duas letras ("ZZ", "ZX"): só dígitos seria qualquer protocolo de 12 dígitos.
    PatternSpec("CC_PT", B + r"\d{8}[ -]?\d[ -]?[A-Z]{2}[ -]?\d" + E, Scores(0.9, None, 0.97, 0.7),
                v.is_valid_cc_pt, CTX_CC_PT),
    PatternSpec("NIF_PT", B + r"\d{3}[ .]?\d{3}[ .]?\d{3}" + E, Scores(None, None, 0.95), v.is_valid_nif_pt, CTX_NIF_PT,
                before=30),
    PatternSpec("NISS_PT", B + r"[12]\d{10}" + E, Scores(None, None, 0.97), v.is_valid_niss_pt, CTX_NISS_PT, before=30),
    PatternSpec("CUIT", B + _CUIT_PREFIX + r"-\d{8}-\d" + E, Scores(0.9, None, 0.97, 0.75), v.is_valid_cuit, CTX_CUIT),
    PatternSpec("CUIT", B + _CUIT_PREFIX + r"\d{9}" + E, Scores(None, None, 0.96), v.is_valid_cuit, CTX_CUIT, before=30),
    PatternSpec("DNI", B + r"\d{1,2}\.?\d{3}\.?\d{3}(?:-[0-9A-K])?" + E, Scores(None, None, 0.85), None, CTX_DNI,
                before=20),
    PatternSpec("CURP", B + r"[A-Z]{4}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d" + E, Scores(0.95, 0.6, 1.0, 0.8), v.is_valid_curp,
                CTX_MX),
    PatternSpec("RFC", r"(?<![\w&])[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}" + E, Scores(0.85, None, 0.97), v.is_valid_rfc, CTX_MX),
    # O RUT chileno e a cédula uruguaia formatados têm o desenho do RG: sem contexto, perdem para ele (0,55 < 0,6).
    PatternSpec("RUT", B + r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]" + E, Scores(0.55, None, 0.97, 0.75), v.is_valid_rut_cl, CTX_RUT),
    PatternSpec("RUT", B + r"\d{7,8}-[\dkK]" + E, Scores(None, None, 0.95, 0.75), v.is_valid_rut_cl, CTX_RUT, before=25),
    PatternSpec("RUT", B + r"\d{12}" + E, Scores(None, None, 0.95), v.is_valid_rut_uy, CTX_RUT, before=25),
    PatternSpec("CEDULA", B + r"\d\.\d{3}\.\d{3}-\d" + E, Scores(0.55, None, 0.97, 0.75), v.is_valid_ci_uy, CTX_CEDULA),
    PatternSpec("CEDULA", B + r"\d{10}" + E, Scores(None, None, 0.95), v.is_valid_ci_ec, CTX_CEDULA, before=25),
    PatternSpec("CEDULA", B + r"(?:\d{1,3}(?:\.\d{3}){1,3}|\d{6,10})" + E, Scores(None, None, 0.85), None, CTX_CEDULA,
                before=20),
    PatternSpec("NIT", B + r"\d{3}\.\d{3}\.\d{3}-\d" + E, Scores(0.8, None, 0.97, 0.75), v.is_valid_nit_co, CTX_NIT),
    PatternSpec("NIT", B + r"\d{8,15}-?\d" + E, Scores(None, None, 0.95, 0.75), v.is_valid_nit_co, CTX_NIT, before=25),
    PatternSpec("RUC", B + r"(?:\d{11}|\d{13}|\d{5,8}-\d)" + E, Scores(None, None, 0.96, 0.75), v.is_valid_ruc, CTX_RUC,
                before=25),
    PatternSpec("RIF", B + r"[VEJPG]-?\d{8}-?\d" + E, Scores(0.9, None, 0.97, 0.75), v.is_valid_rif, CTX_RIF),
    # África lusófona, EUA, Europa, Índia e identificadores transversais.
    PatternSpec("NUIT", B + r"\d{3}\s?\d{3}\s?\d{3}" + E, Scores(None, None, 0.95), v.is_valid_nuit, CTX_NUIT, before=30),
    PatternSpec("BI_AO", B + r"\d{9}[A-Z]{2}\d{3}" + E, Scores(0.85, None, 0.97), None, CTX_BI_AFRICA),
    # 12 dígitos e uma letra também é o formato das datas de certificados X.509 ("261108123045Z"): só com contexto.
    PatternSpec("BI_MZ", B + r"\d{12}[A-Z]" + E, Scores(None, None, 0.95), None, CTX_BI_AFRICA, before=30),
    PatternSpec("SSN", B + r"\d{3}-\d{2}-\d{4}" + E, Scores(0.85, None, 0.97), v.is_valid_ssn, CTX_SSN),
    PatternSpec("SSN", B + r"\d{3}\s?\d{2}\s?\d{4}" + E, Scores(None, None, 0.95), v.is_valid_ssn, CTX_SSN, before=30),
    PatternSpec("MBI", B + r"[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y\d]\d-?[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y\d]\d-?"
                r"[AC-HJKMNP-RT-Y]{2}\d{2}" + E, Scores(None, None, 0.95), None, CTX_MBI, before=30),
    PatternSpec("DNI_ES", B + r"[XYZ]?\d{7,8}-?[A-Z]" + E, Scores(0.85, None, 0.97), v.is_valid_dni_es, CTX_DNI_ES),
    PatternSpec("CODICE_FISCALE", B + r"[A-Z]{6}[\dLMNP-V]{2}[ABCDEHLMPRST][\dLMNP-V]{2}[A-Z][\dLMNP-V]{3}[A-Z]" + E,
                Scores(0.95, 0.6, 1.0, 0.8), v.is_valid_codice_fiscale, CTX_CF),
    # Sem os espaços, 15 dígitos começando com 1 ou 2 podem ser um protocolo: só com contexto.
    PatternSpec("NIR", B + r"[12] \d{2} \d{2} (?:\d{2}|2[AB]) \d{3} \d{3} \d{2}" + E, Scores(0.85, None, 0.97), v.is_valid_nir,
                CTX_NIR),
    PatternSpec("NIR", B + r"[12]\d{4}(?:\d{2}|2[AB])\d{8}" + E, Scores(None, None, 0.95), v.is_valid_nir, CTX_NIR, before=30),
    PatternSpec("STEUER_ID", B + r"\d{2}\s?\d{3}\s?\d{3}\s?\d{3}" + E, Scores(None, None, 0.95), v.is_valid_steuer_id,
                CTX_STEUER, before=35),
    PatternSpec("NINO", B + r"[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]" + E,
                Scores(0.85, None, 0.97), v.is_valid_nino, CTX_NINO),
    PatternSpec("NINO", B + r"[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}" + E, Scores(None, None, 0.95),
                v.is_valid_nino, CTX_NINO, before=30),
    PatternSpec("NHS", B + r"\d{3}\s?\d{3}\s?\d{4}" + E, Scores(None, None, 0.95), v.is_valid_nhs, CTX_NHS, before=30),
    PatternSpec("BSN", B + r"\d{9}" + E, Scores(None, None, 0.95), v.is_valid_bsn, CTX_BSN, before=30),
    PatternSpec("SIN", B + r"\d{3}[\s-]?\d{3}[\s-]?\d{3}" + E, Scores(None, None, 0.95), v.is_valid_sin, CTX_SIN, before=30),
    PatternSpec("AADHAAR", B + r"[2-9]\d{3}\s?\d{4}\s?\d{4}" + E, Scores(None, None, 0.95), v.is_valid_aadhaar, CTX_AADHAAR,
                before=30),
    PatternSpec("PAN", B + r"[A-Z]{3}[PCHFATBLJGK][A-Z]\d{4}[A-Z]" + E, Scores(None, None, 0.95), None, CTX_PAN, before=30),
    # MRZ de passaporte (TD3): a 1ª linha traz o nome; a 2ª, número, nascimento e validade com dígitos verificadores.
    PatternSpec("MRZ", r"(?<![A-Z0-9<])P[A-Z<][A-Z<]{3}[A-Z<]{39}(?![A-Z0-9<])", Scores(0.9, None, 0.97), _mrz_name_line,
                CTX_MRZ),
    PatternSpec("MRZ", r"(?<![A-Z0-9<])[A-Z0-9<]{9}\d[A-Z<]{3}\d{7}[MFX<]\d{7}[A-Z0-9<]{14}[\d<]\d(?![A-Z0-9<])",
                Scores(0.95, None, 1.0), v.is_valid_mrz_line, CTX_MRZ),
    # Chassi: o dígito da posição 9 só é obrigatório nos EUA e na China; sem ele, só com "chassi" ou "VIN" por perto.
    PatternSpec("VIN", B + r"[A-HJ-NPR-Z0-9]{17}" + E, Scores(0.85, None, 0.97, 0.8), v.is_valid_vin, CTX_VIN,
                exclude=lambda value: value.isdigit() or value.isalpha()),
    PatternSpec("CRIPTO", r"(?<![\w])(?:0x[0-9a-fA-F]{40}|[13][1-9A-HJ-NP-Za-km-z]{25,34}|(?:bc|tb)1[02-9ac-hj-np-z]{11,71})"
                + E, Scores(0.9, None, 0.97), v.is_valid_crypto_address, CTX_CRYPTO),
    # TRON (USDT TRC20), Litecoin, Dogecoin e chaves públicas estendidas (xpub), todos pelo checksum Base58Check.
    PatternSpec("CRIPTO", r"(?<![\w])(?:[TLMD][1-9A-HJ-NP-Za-km-z]{26,34}|[xyzt]pub[1-9A-HJ-NP-Za-km-z]{100,112}"
                r"|ltc1[02-9ac-hj-np-z]{11,71})" + E, Scores(0.9, None, 0.97), v.is_valid_crypto_address, CTX_CRYPTO,
                name="carteiras"),
    # Chave privada de Bitcoin: WIF ("5Hue...", "KwDi...") e estendida (xprv), pelo checksum.
    PatternSpec("CHAVE_PRIVADA", r"(?<![\w])(?:[59KLc][1-9A-HJ-NP-Za-km-z]{50,51}|[xyzt]prv[1-9A-HJ-NP-Za-km-z]{100,112})"
                + E, Scores(0.99), v.is_valid_crypto_private_key, name="cripto"),
    # Chave privada de Ethereum (64 hexadecimais) só com "chave privada"/"private key" por perto: hashes ficam.
    PatternSpec("CHAVE_PRIVADA", r"(?<![\w])(?:0x)?[0-9a-fA-F]{64}" + E, Scores(None, None, 0.9), None, CTX_PRIVATE_KEY,
                before=50, name="cripto"),
    # Infraestrutura. Uma porta é só um número: vale colada a um IP ou a um servidor, depois de "porta"/"port" ou
    # numa opção de comando (-p), nunca solta. O grupo "valor" é o que vira o marcador; o resto é só o contexto.
    PatternSpec("PORTA", B + r"(?:\d{1,3}\.){3}\d{1,3}:(?P<valor>\d{2,5})" + E, Scores(0.9), v.is_valid_port),
    PatternSpec("PORTA", r"\[[0-9A-Fa-f:.]{3,45}\]:(?P<valor>\d{2,5})" + E, Scores(0.9), v.is_valid_port),
    PatternSpec("PORTA", r"://(?:[^\s/@]{1,200}@)?[A-Za-z0-9.-]{1,253}:(?P<valor>\d{2,5})" + E, Scores(0.9),
                v.is_valid_port),
    PatternSpec("PORTA", r"(?<![\w.@-])(?:localhost|(?:[A-Za-z0-9-]+\.)+" + _INTERNAL_TLDS + r"):(?P<valor>\d{2,5})" + E,
                Scores(0.9), v.is_valid_port, flags=re.IGNORECASE),
    PatternSpec("PORTA", r"(?<![\w.@/-])(?=[A-Za-z0-9.-]*[A-Za-z])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}:(?P<valor>\d{2,5})" + E,
                Scores(None, None, 0.85), v.is_valid_port, CTX_HOST),
    PatternSpec("PORTA", r"(?<![A-Za-z])(?:portas?|ports?|--port)[\"']?\s*(?:[:=]\s*|n[ºo°]\.?\s*)?(?P<valor>\d{2,5})" + E,
                Scores(0.85), v.is_valid_port, flags=re.IGNORECASE),
    PatternSpec("PORTA", r"(?<![\w-])-[pP]\s+(?P<valor>\d{2,5})" + E, Scores(None, None, 0.85), v.is_valid_port,
                CTX_SHELL, before=60),
    PatternSpec("PORTA", r"(?<![\w-])-[pP]\s+\d{2,5}:(?P<valor>\d{2,5})" + E, Scores(None, None, 0.85), v.is_valid_port,
                CTX_SHELL, before=60),
    # Endereço MAC de placa de rede ("95:7F:76:CE:A3:DA", "1c-bb-bd-4a-58-ad", "aabb.ccdd.eeff").
    PatternSpec("MAC", r"(?<![\w:.-])[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}(?![\w:.-])", Scores(0.85), v.is_valid_mac,
                CTX_MAC),
    PatternSpec("MAC", r"(?<![\w:.-])[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5}(?![\w:.-])", Scores(0.85), v.is_valid_mac,
                CTX_MAC),
    PatternSpec("MAC", r"(?<![\w.:-])[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}(?![\w.:-])", Scores(None, None, 0.85),
                v.is_valid_mac, CTX_MAC),
    PatternSpec("SERVIDOR", r"(?<![\w.@-])(?:[A-Za-z0-9-]+\.)+" + _INTERNAL_TLDS + r"(?![\w-]|\.[A-Za-z])", Scores(0.85),
                flags=re.IGNORECASE),
]


class PatternRecognizer:
    """Acha dados pessoais por expressões regulares, valida e pontua pelo contexto."""

    name = "padroes"

    def __init__(self, specs: Iterable[PatternSpec] | None = None):
        self.specs = list(DEFAULT_SPECS if specs is None else specs)
        self.labels = frozenset(spec.label for spec in self.specs)

    def find(self, text: str) -> Iterable[Candidate]:
        folded: str | None = None
        for spec in self.specs:
            # Padrões que só valem com contexto: sem nenhuma palavra de contexto no texto, nem procura os números.
            if spec.scores.valid is None and spec.scores.invalid is None and spec.context_regex is not None:
                folded = fold(text) if folded is None else folded
                if spec.context_regex.search(folded) is None:
                    continue
            # Com um grupo "valor", só ele é o dado (a porta em "10.0.0.5:8080"); o resto do padrão é contexto.
            group = "valor" if "valor" in spec.compiled.groupindex else 0
            for match in spec.compiled.finditer(text):
                value = match.group(group)
                start, end = match.span(group)
                if spec.exclude and spec.exclude(value):
                    continue
                is_valid = spec.validator(value) if spec.validator else True
                has_context = False
                if spec.context_regex is not None:
                    window = context_window(text, start, end, spec.before, spec.after)
                    has_context = spec.context_regex.search(window) is not None
                if not has_context and spec.exclude_at and spec.exclude_at(text, start, end):
                    continue
                score = spec.scores.pick(is_valid, has_context)
                if score is not None and spec.adjust:
                    score = spec.adjust(value, score)
                if score is None or score <= 0:
                    continue
                yield Candidate(spec.label, start, end, round(score, 3), spec.name or self.name)


def custom_spec(label: str, pattern: str, score: float = 0.9, context: Iterable[str] = (),
                requires_context: bool = False) -> PatternSpec:
    """Padrão definido pelo usuário (seção [[deteccao.personalizados]] do veu.toml)."""
    words = tuple(fold(word) for word in context)
    scores = Scores(None, None, score) if requires_context else Scores(score, None, min(1.0, score + 0.1))
    return PatternSpec(label.upper(), pattern, scores, None, words, name="personalizado")
