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
