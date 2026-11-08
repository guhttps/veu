"""Validação de documentos brasileiros pelos dígitos verificadores.

Os validadores reduzem falsos positivos: um número de 11 dígitos só é tratado
como CPF com alta confiança se os dígitos verificadores baterem.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date

from veu._text import only_digits

# DDDs em uso no Brasil (Anatel).
VALID_DDDS = frozenset({
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55,
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
})

_CNPJ_CLEAN = re.compile(r"[^0-9A-Za-z]")
_CNPJ_W1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_W2 = (6, *_CNPJ_W1)


def _mod11(values, weights) -> int:
    rest = sum(value * weight for value, weight in zip(values, weights, strict=True)) % 11
    return 0 if rest < 2 else 11 - rest


def _repeated(digits: str) -> bool:
    return len(set(digits)) == 1


def cpf_check_digits(base: str) -> str:
    """Dígitos verificadores dos 9 primeiros dígitos de um CPF."""
    values = [int(char) for char in base]
    first = _mod11(values, range(10, 1, -1))
    second = _mod11([*values, first], range(11, 1, -1))
    return f"{first}{second}"


def is_valid_cpf(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or _repeated(digits):
        return False
    return cpf_check_digits(digits[:9]) == digits[9:]


def normalize_cnpj(value: str) -> str:
    return _CNPJ_CLEAN.sub("", value).upper()


def cnpj_check_digits(base: str) -> str:
    """Dígitos verificadores dos 12 primeiros caracteres de um CNPJ.

    Funciona para o CNPJ numérico e para o alfanumérico (em vigor desde julho de 2026):
    cada caractere vale o seu código ASCII menos 48, então "0".."9" valem 0..9 e "A".."Z" valem 17..42.
    """
    values = [ord(char) - 48 for char in base.upper()]
    first = _mod11(values, _CNPJ_W1)
    second = _mod11([*values, first], _CNPJ_W2)
    return f"{first}{second}"


def is_valid_cnpj(value: str) -> bool:
    cnpj = normalize_cnpj(value)
    if len(cnpj) != 14 or not cnpj[12:].isdigit():
        return False
    if not all(char.isdigit() or "A" <= char <= "Z" for char in cnpj[:12]):
        return False
    if cnpj.isdigit() and _repeated(cnpj):
        return False
    return cnpj_check_digits(cnpj[:12]) == cnpj[12:]


def pis_check_digit(base: str) -> str:
    rest = sum(int(char) * weight for char, weight in zip(base, (3, 2, 9, 8, 7, 6, 5, 4, 3, 2), strict=True)) % 11
    digit = 11 - rest
    return "0" if digit >= 10 else str(digit)


def is_valid_pis(value: str) -> bool:
    """PIS, PASEP, NIT e NIS usam o mesmo cálculo."""
    digits = only_digits(value)
    if len(digits) != 11 or _repeated(digits):
        return False
    return pis_check_digit(digits[:10]) == digits[10]


def cnh_check_digits(base: str) -> str:
    values = [int(char) for char in base]
    first = sum(value * weight for value, weight in zip(values, range(9, 0, -1), strict=True)) % 11
    discount = 0
    if first >= 10:
        first, discount = 0, 2
    second = sum(value * weight for value, weight in zip(values, range(1, 10), strict=True)) % 11 - discount
    if second < 0:
        second += 11
    if second >= 10:
        second = 0
    return f"{first}{second}"


def is_valid_cnh(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or _repeated(digits):
        return False
    return cnh_check_digits(digits[:9]) == digits[9:]


def titulo_check_digits(base: str) -> str:
    """Dígitos do título de eleitor: 8 dígitos sequenciais + 2 do código da UF."""
    values = [int(char) for char in base]
    uf = values[8] * 10 + values[9]
    first = sum(value * weight for value, weight in zip(values[:8], range(2, 10), strict=True)) % 11
    if first == 10:
        first = 0
    elif first == 0 and uf in (1, 2):
        first = 1
    second = (values[8] * 7 + values[9] * 8 + first * 9) % 11
    if second == 10:
        second = 0
    elif second == 0 and uf in (1, 2):
        second = 1
    return f"{first}{second}"


def is_valid_titulo_eleitor(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 12 or _repeated(digits):
        return False
    if not 1 <= int(digits[8:10]) <= 28:
        return False
    return titulo_check_digits(digits[:10]) == digits[10:]


def is_valid_cns(value: str) -> bool:
    """Cartão Nacional de Saúde (SUS): 15 dígitos, soma ponderada divisível por 11."""
    digits = only_digits(value)
    if len(digits) != 15 or digits[0] not in "12789":
        return False
    return sum(int(char) * weight for char, weight in zip(digits, range(15, 0, -1), strict=True)) % 11 == 0


def renavam_check_digit(base: str) -> str:
    total = sum(int(char) * weight for char, weight in zip(base, (3, 2, 9, 8, 7, 6, 5, 4, 3, 2), strict=True))
    digit = (total * 10) % 11
    return "0" if digit == 10 else str(digit)


def is_valid_renavam(value: str) -> bool:
    digits = only_digits(value)
    if not 9 <= len(digits) <= 11:
        return False
    digits = digits.zfill(11)
    if _repeated(digits):
        return False
    return renavam_check_digit(digits[:10]) == digits[10]


def is_valid_luhn(value: str) -> bool:
    digits = only_digits(value)
    if not 13 <= len(digits) <= 19 or _repeated(digits):
        return False
    total = 0
    for position, char in enumerate(reversed(digits)):
        number = int(char)
        if position % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def is_valid_card(value: str) -> bool:
    """Cartão de crédito/débito: Luhn e prefixo de uma bandeira conhecida."""
    digits = only_digits(value)
    if not is_valid_luhn(digits) or digits[0] not in "23456":
        return False
    # Números de 14 e 15 dígitos válidos como CNPJ ou cartão do SUS ficam com esses rótulos.
    return not (len(digits) == 14 and is_valid_cnpj(digits)) and not (len(digits) == 15 and is_valid_cns(digits))


def cnj_check_digits(number: str, year: str, segment: str, court: str, origin: str) -> str:
    rest = int(f"{number}{year}{segment}{court}{origin}00") % 97
    return f"{98 - rest:02d}"


def is_valid_processo_cnj(value: str) -> bool:
    """Número único de processo do CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO (Resolução CNJ 65/2008)."""
    digits = only_digits(value)
    if len(digits) != 20:
        return False
    number, check, year, segment, court, origin = (
        digits[:7], digits[7:9], digits[9:13], digits[13], digits[14:16], digits[16:],
    )
    return cnj_check_digits(number, year, segment, court, origin) == check


def phone_digits(value: str) -> str:
    """Dígitos do telefone sem o código do país."""
    digits = only_digits(value)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    return digits


def is_valid_phone(value: str) -> bool:
    """Celular (DDD + 9 dígitos começando com 9) ou fixo (DDD + 8 dígitos começando com 2 a 5)."""
    digits = phone_digits(value)
    if len(digits) == 11:
        return int(digits[:2]) in VALID_DDDS and digits[2] == "9" and not _repeated(digits[3:])
    if len(digits) == 10:
        return int(digits[:2]) in VALID_DDDS and digits[2] in "2345" and not _repeated(digits[2:])
    return False


def is_valid_iban(value: str) -> bool:
    """IBAN pelo módulo 97 (ISO 13616). Vale para qualquer país, inclusive o Brasil (BR + 27 caracteres)."""
    compact = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    number = "".join(str(int(char, 36)) for char in rearranged)
    return int(number) % 97 == 1


def is_valid_intl_phone(value: str) -> bool:
    """Telefone em formato internacional (+código do país): de 8 a 15 dígitos, sem repetição óbvia."""
    digits = only_digits(value)
    return 8 <= len(digits) <= 15 and not _repeated(digits[-8:])


def is_valid_ipv4(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return not (address.is_loopback or address.is_unspecified)


def is_valid_ipv6(value: str) -> bool:
    if value.count(":") < 2:
        return False
    try:
        address = ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return not (address.is_loopback or address.is_unspecified)


MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def parse_date(value: str) -> date | None:
    text = value.strip().lower()
    match = re.fullmatch(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", text)
    if match:
        day, month, year = int(match[1]), MONTHS.get(match[2]), int(match[3])
    else:
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if match:
            year, month, day = int(match[1]), int(match[2]), int(match[3])
        else:
            match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})", text)
            if not match:
                return None
            day, month, year = int(match[1]), int(match[2]), int(match[3])
            if year < 100:
                year += 1900 if year > 30 else 2000
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_plausible_birthdate(value: str) -> bool:
    parsed = parse_date(value)
    return parsed is not None and 1900 <= parsed.year <= date.today().year


# Outros países ---------------------------------------------------------------------------------------------------
# Algoritmos conferidos com o python-stdnum 2.2 (usado só como referência; não é dependência do Véu).

_NIF_PT_PREFIXES = frozenset({"45", "70", "71", "72", "74", "75", "77", "78", "79", "90", "91", "98", "99"})


def is_valid_nif_pt(value: str) -> bool:
    """NIF/NIPC de Portugal: 9 dígitos, mod 11, com os prefixos que existem."""
    d = only_digits(value)
    if len(d) != 9 or not (d[0] in "12356" or d[:2] in _NIF_PT_PREFIXES):
        return False
    total = sum((9 - i) * int(n) for i, n in enumerate(d[:8]))
    return str((11 - total) % 11 % 10) == d[8]


_ALNUM36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_valid_cc_pt(value: str) -> bool:
    """Número do Cartão de Cidadão (Portugal): 8 dígitos, 1 dígito, 2 caracteres de versão e o controlo final."""
    compact = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"\d{9}[A-Z0-9]{2}\d", compact):
        return False
    total = 0
    for index, char in enumerate(compact[:-1][::-1]):
        number = _ALNUM36.index(char)
        if index % 2 == 0:
            number *= 2
            number = number - 9 if number > 9 else number
        total += number
    return str((10 - total) % 10) == compact[-1]


def is_valid_niss_pt(value: str) -> bool:
    """NISS de Portugal: 11 dígitos, começa com 1 ou 2, pesos primos."""
    d = only_digits(value)
    if len(d) != 11 or d[0] not in "12":
        return False
    weights = (29, 23, 19, 17, 13, 11, 7, 5, 3, 2)
    return str(9 - sum(w * int(n) for w, n in zip(weights, d[:10], strict=True)) % 10) == d[10]


_CUIT_PREFIXES = frozenset({"20", "23", "24", "27", "30", "33", "34", "50", "51", "55"})


def is_valid_cuit(value: str) -> bool:
    """CUIT/CUIL da Argentina: 11 dígitos, prefixo conhecido, mod 11."""
    d = only_digits(value)
    if len(d) != 11 or d[:2] not in _CUIT_PREFIXES:
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(w * int(n) for w, n in zip(weights, d[:10], strict=True))
    return "012345678990"[11 - total % 11] == d[10]


_CURP_ALPHABET = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ"
_MX_STATES = frozenset({
    "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR", "HG", "JC", "MC", "MN", "MS", "NT", "NL",
    "OC", "PL", "QT", "QR", "SP", "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE",
})


def _valid_yymmdd(text: str) -> bool:
    month, day = int(text[2:4]), int(text[4:6])
    if not 1 <= month <= 12:
        return False
    try:
        date(2000, month, day)  # ano bissexto: aceita 29/02
    except ValueError:
        return False
    return True


def is_valid_curp(value: str) -> bool:
    """CURP do México: data, sexo, estado e dígito verificador."""
    v = value.upper()
    if not re.fullmatch(r"[A-Z]{4}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d", v):
        return False
    if not _valid_yymmdd(v[4:10]) or v[11:13] not in _MX_STATES:
        return False
    total = sum(_CURP_ALPHABET.index(char) * (18 - i) for i, char in enumerate(v[:17]))
    return str((10 - total % 10) % 10) == v[17]


_RFC_GENERIC = frozenset({"XAXX010101000", "XEXX010101000"})


def is_valid_rfc(value: str) -> bool:
    """RFC do México (pessoa física ou moral): data válida; os RFCs genéricos de "público em geral" não contam."""
    v = value.upper()
    if v in _RFC_GENERIC or not re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", v):
        return False
    return _valid_yymmdd(v[-9:-3])


def is_valid_rut_cl(value: str) -> bool:
    """RUT/RUN do Chile: até 8 dígitos e o verificador (0 a 9 ou K), mod 11."""
    compact = re.sub(r"[.\s-]", "", value).upper()
    if not re.fullmatch(r"\d{6,8}[0-9K]", compact):
        return False
    body, check = compact[:-1], compact[-1]
    total = sum(int(n) * (2 + i % 6) for i, n in enumerate(reversed(body)))
    rest = 11 - total % 11
    return {11: "0", 10: "K"}.get(rest, str(rest)) == check


def is_valid_ci_uy(value: str) -> bool:
    """Cédula de identidade do Uruguai: 7 dígitos e o verificador."""
    d = only_digits(value)
    if len(d) != 8:
        return False
    total = sum(w * int(n) for w, n in zip((2, 9, 8, 7, 6, 3, 4), d[:7], strict=True))
    return str((10 - total % 10) % 10) == d[7]


def is_valid_rut_uy(value: str) -> bool:
    """RUT do Uruguai: 12 dígitos (registro 01 a 22, sequência, 001 e o verificador)."""
    d = only_digits(value)
    if len(d) != 12 or not 1 <= int(d[:2]) <= 22 or d[2:8] == "000000" or d[8:11] != "001":
        return False
    weights = (4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    check = -sum(w * int(n) for w, n in zip(weights, d[:11], strict=True)) % 11
    return check != 10 and str(check) == d[11]


_NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def is_valid_nit_co(value: str) -> bool:
    """NIT da Colômbia: 8 a 16 dígitos, pesos primos a partir da direita."""
    d = only_digits(value)
    if not 8 <= len(d) <= 16:
        return False
    total = sum(w * int(n) for w, n in zip(_NIT_WEIGHTS, reversed(d[:-1]), strict=False))
    return "01987654321"[total % 11] == d[-1]


def is_valid_ruc_pe(value: str) -> bool:
    """RUC do Peru: 11 dígitos, prefixo 10, 15, 17 ou 20."""
    d = only_digits(value)
    if len(d) != 11 or d[:2] not in ("10", "15", "17", "20"):
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    return str((11 - sum(w * int(n) for w, n in zip(weights, d[:10], strict=True)) % 11) % 10) == d[10]


def is_valid_ci_ec(value: str) -> bool:
    """Cédula do Equador: 10 dígitos, província válida e verificador."""
    d = only_digits(value)
    if len(d) != 10 or not (1 <= int(d[:2]) <= 24 or d[:2] in ("30", "50")) or int(d[2]) >= 6:
        return False
    total = 0
    for i, n in enumerate(d[:9]):
        product = int(n) * (2 if i % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    return str((10 - total % 10) % 10) == d[9]


def is_valid_ruc_ec(value: str) -> bool:
    """RUC do Equador: 13 dígitos (pessoa natural, setor público ou pessoa jurídica)."""
    d = only_digits(value)
    if len(d) != 13 or not (1 <= int(d[:2]) <= 24 or d[:2] in ("30", "50")):
        return False
    if int(d[2]) < 6:
        return is_valid_ci_ec(d[:10]) and d[10:] != "000"
    if d[2] == "6":
        weights = (3, 2, 7, 6, 5, 4, 3, 2, 1)
        return sum(w * int(n) for w, n in zip(weights, d[:9], strict=True)) % 11 == 0 and d[9:] != "0000"
    if d[2] == "9":
        weights = (4, 3, 2, 7, 6, 5, 4, 3, 2, 1)
        return sum(w * int(n) for w, n in zip(weights, d[:10], strict=True)) % 11 == 0 and d[10:] != "000"
    return False


def is_valid_ruc_py(value: str) -> bool:
    """RUC do Paraguai: até 8 dígitos e o verificador."""
    d = only_digits(value)
    if not 6 <= len(d) <= 9:
        return False
    total = sum(int(n) * (2 + i) for i, n in enumerate(reversed(d[:-1])))
    return str((-total % 11) % 10) == d[-1]


def is_valid_ruc(value: str) -> bool:
    """RUC do Peru, do Equador ou do Paraguai (o formato decide qual conferir)."""
    return is_valid_ruc_pe(value) or is_valid_ruc_ec(value) or is_valid_ruc_py(value)


def is_valid_cedula(value: str) -> bool:
    """Cédula do Uruguai ou do Equador."""
    return is_valid_ci_uy(value) or is_valid_ci_ec(value)


_RIF_LETTERS = {"V": 4, "E": 8, "J": 12, "P": 16, "G": 20}


def is_valid_rif(value: str) -> bool:
    """RIF da Venezuela: letra (V, E, J, P ou G), 8 dígitos e o verificador."""
    compact = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"[VEJPG]\d{9}", compact):
        return False
    weights = (3, 2, 7, 6, 5, 4, 3, 2)
    total = _RIF_LETTERS[compact[0]] + sum(w * int(n) for w, n in zip(weights, compact[1:9], strict=True))
    return "00987654321"[total % 11] == compact[9]


# África lusófona, EUA, Europa e identificadores transversais (python-stdnum 2.2 como referência) -----------------

def is_valid_nuit(value: str) -> bool:
    """NUIT de Moçambique: 9 dígitos, mod 11."""
    d = only_digits(value)
    if len(d) != 9:
        return False
    total = sum(w * int(n) for w, n in zip((8, 9, 4, 5, 6, 7, 8, 9), d[:8], strict=True))
    return "01234567891"[total % 11] == d[8]


_SSN_BLACKLIST = frozenset({"078051120", "457555462", "219099999"})


def is_valid_ssn(value: str) -> bool:
    """SSN ou ITIN dos EUA: sem dígito verificador, só as faixas que existem."""
    d = only_digits(value)
    if len(d) != 9 or d in _SSN_BLACKLIST:
        return False
    area, group, serial = d[:3], d[3:5], d[5:]
    if area[0] == "9":  # ITIN: começa com 9 e o grupo fica entre 70 e 99 (menos 89 e 93)
        return 70 <= int(group) <= 99 and group not in ("89", "93")
    return area not in ("000", "666") and group != "00" and serial != "0000"


_DNI_ES_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def is_valid_dni_es(value: str) -> bool:
    """DNI ou NIE da Espanha: a letra final é o resto da divisão por 23."""
    compact = re.sub(r"[\s-]", "", value).upper()
    match = re.fullmatch(r"([XYZ]?)(\d{7,8})([A-Z])", compact)
    if not match:
        return False
    prefix, number, letter = match.groups()
    if prefix:
        if len(number) != 7:
            return False
        number = str("XYZ".index(prefix)) + number
    elif len(number) != 8:
        return False
    return _DNI_ES_LETTERS[int(number) % 23] == letter


_CF_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   (1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8,
                    12, 14, 16, 10, 22, 25, 24, 23), strict=True))
_CF_EVEN = {**{str(i): i for i in range(10)}, **{chr(65 + i): i for i in range(26)}}


def is_valid_codice_fiscale(value: str) -> bool:
    """Codice fiscale da Itália: 16 caracteres com estrutura fixa e caractere de controle."""
    v = value.upper()
    if not re.fullmatch(r"[A-Z]{6}[\dLMNP-V]{2}[ABCDEHLMPRST][\dLMNP-V]{2}[A-Z][\dLMNP-V]{3}[A-Z]", v):
        return False
    total = sum(_CF_ODD[c] if i % 2 == 0 else _CF_EVEN[c] for i, c in enumerate(v[:15]))
    return chr(65 + total % 26) == v[15]


def is_valid_nir(value: str) -> bool:
    """NIR (número de segurança social) da França: 15 caracteres, chave = 97 − (número mod 97)."""
    compact = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"[12]\d{4}(?:\d{2}|2A|2B)\d{6}\d{2}", compact):
        return False
    number = compact[:13].replace("2A", "19").replace("2B", "18")
    return 97 - int(number) % 97 == int(compact[13:])


def is_valid_steuer_id(value: str) -> bool:
    """Steuer-IdNr da Alemanha: 11 dígitos, um algarismo repetido, ISO 7064 MOD 11,10."""
    d = only_digits(value)
    if len(d) != 11 or d[0] == "0":
        return False
    counts = sorted(d[:10].count(n) for n in set(d[:10]))
    if counts.count(2) + counts.count(3) != 1 or max(counts) > 3:
        return False
    check = 10
    for n in d[:10]:
        check = (int(n) + check) % 10 or 10
        check = (check * 2) % 11
    return (11 - check) % 10 == int(d[10])


_NINO_PREFIX_BAD = frozenset({"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"})


def is_valid_nino(value: str) -> bool:
    """National Insurance Number do Reino Unido: regras de formato da HMRC (sem dígito verificador)."""
    compact = re.sub(r"\s", "", value).upper()
    match = re.fullmatch(r"([A-CEGHJ-PR-TW-Z])([A-CEGHJ-NPR-TW-Z])(\d{6})([A-D]?)", compact)
    return bool(match) and match.group(1) + match.group(2) not in _NINO_PREFIX_BAD


def is_valid_nhs(value: str) -> bool:
    """Número do NHS (Reino Unido): 10 dígitos, mod 11."""
    d = only_digits(value)
    if len(d) != 10:
        return False
    check = 11 - sum((10 - i) * int(n) for i, n in enumerate(d[:9])) % 11
    return check != 10 and str(0 if check == 11 else check) == d[9]


def is_valid_bsn(value: str) -> bool:
    """BSN dos Países Baixos: prova dos 11."""
    d = only_digits(value).zfill(9)
    if len(d) != 9 or d == "000000000":
        return False
    return (sum((9 - i) * int(n) for i, n in enumerate(d[:8])) - int(d[8])) % 11 == 0


def is_valid_sin(value: str) -> bool:
    """SIN do Canadá: 9 dígitos com Luhn; não começa com 0 nem 8."""
    d = only_digits(value)
    if len(d) != 9 or d[0] in "08":
        return False
    total = sum(int(n) if i % 2 == 0 else (int(n) * 2 - 9 if int(n) * 2 > 9 else int(n) * 2) for i, n in enumerate(d))
    return total % 10 == 0


_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def is_valid_aadhaar(value: str) -> bool:
    """Aadhaar da Índia: 12 dígitos, não começa com 0 ou 1, não é palíndromo, dígito Verhoeff."""
    d = only_digits(value)
    if len(d) != 12 or d[0] in "01" or d == d[::-1]:
        return False
    check = 0
    for i, n in enumerate(reversed(d)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(n)]]
    return check == 0


def _mrz_value(char: str) -> int:
    if char.isdigit():
        return int(char)
    if char == "<":
        return 0
    return ord(char) - 55


def mrz_check_digit(field: str) -> str:
    return str(sum(_mrz_value(c) * (7, 3, 1)[i % 3] for i, c in enumerate(field)) % 10)


def is_valid_mrz_line(value: str) -> bool:
    """2ª linha da MRZ de passaporte (ICAO 9303, TD3): número, nascimento e validade com dígitos 7-3-1."""
    line = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"[A-Z0-9<]{9}\d[A-Z<]{3}\d{6}\d[MFX<]\d{6}\d[A-Z0-9<]{14}[\d<]\d", line):
        return False
    return (mrz_check_digit(line[0:9]) == line[9] and mrz_check_digit(line[13:19]) == line[19]
            and mrz_check_digit(line[21:27]) == line[27]
            and mrz_check_digit(line[0:10] + line[13:20] + line[21:43]) == line[43])


_VIN_VALUES = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9), strict=True)),
               **dict(zip("JKLMN", range(1, 6), strict=True)), "P": 7, "R": 9,
               **dict(zip("STUVWXYZ", range(2, 10), strict=True))}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def is_valid_vin(value: str) -> bool:
    """VIN (chassi): 17 caracteres sem I, O e Q, com o dígito verificador da posição 9."""
    v = value.upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", v) or not re.search(r"\d", v) or not re.search(r"[A-Z]", v):
        return False
    check = sum(_VIN_VALUES[c] * w for c, w in zip(v, _VIN_WEIGHTS, strict=True)) % 11
    return ("X" if check == 10 else str(check)) == v[8]


_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58check_ok(value: str) -> bool:
    import hashlib

    number = 0
    for char in value:
        number = number * 58 + _BASE58.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\x00" * (len(value) - len(value.lstrip("1"))) + raw
    if len(raw) != 25:
        return False
    digest = hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()
    return digest[:4] == raw[-4:]


_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_ok(value: str) -> bool:
    lower = value.lower()
    hrp, _, data = lower.rpartition("1")
    if hrp not in ("bc", "tb") or len(data) < 6 or any(c not in _BECH32 for c in data):
        return False
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + [_BECH32.index(c) for c in data]
    check = 1
    for v in values:
        top = check >> 25
        check = (check & 0x1FFFFFF) << 5 ^ v
        for i, generator in enumerate((0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)):
            if (top >> i) & 1:
                check ^= generator
    return check in (1, 0x2BC830A3)  # bech32 (v0) e bech32m (Taproot)


def is_valid_crypto_address(value: str) -> bool:
    """Endereço de carteira: Bitcoin (Base58Check ou bech32) ou Ethereum (0x + 40 hexadecimais)."""
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        return True
    if re.fullmatch(r"[13][1-9A-HJ-NP-Za-km-z]{25,34}", value):
        return _base58check_ok(value)
    if re.fullmatch(r"(?:bc|tb)1[02-9ac-hj-np-z]{11,71}", value.lower()) and (value.islower() or value.isupper()):
        return _bech32_ok(value)
    return False
