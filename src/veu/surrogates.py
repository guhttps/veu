"""Geradores de dados pessoais falsos, mas válidos e verossímeis.

Usados pelo operador "sintetico" (o modelo recebe outro CPF válido em vez de [CPF_1]) e pelo
gerador do benchmark. Nenhum valor gerado pertence intencionalmente a uma pessoa real.
"""

from __future__ import annotations

import random
import re
import uuid
from datetime import date, timedelta

from veu import validators as v
from veu._text import fold, only_digits
from veu.recognizers.base import folded_set, load_wordlist

_MONTH_NAMES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_STREET_TYPES = ("Rua", "Avenida", "Travessa", "Alameda")


def first_names() -> list[str]:
    ambiguous = folded_set("ambiguous.txt")
    return [name for name in load_wordlist("first_names.txt") if fold(name) not in ambiguous]


def surnames() -> list[str]:
    return [name for name in load_wordlist("surnames.txt") if fold(name) not in folded_set("ambiguous.txt")]


def apply_format(template: str, characters: str) -> str:
    """Põe os caracteres novos nas posições alfanuméricas do modelo: ("529.982.247-25", "11144477735")."""
    replacement = iter(characters)
    output = []
    for char in template:
        output.append(next(replacement, char) if char.isalnum() else char)
    return "".join(output)


def _digits(rng: random.Random, count: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(count))


def fake_name(rng: random.Random, words: int = 2) -> str:
    parts = [rng.choice(first_names())]
    if words >= 3 and rng.random() < 0.5:
        parts.append(rng.choice(first_names()))
    family = surnames()
    while len(parts) < max(words, 1):
        surname = rng.choice(family)
        if surname not in parts:
            parts.append(surname)
    if words >= 3 and rng.random() < 0.3:
        parts.insert(-1, rng.choice(("da", "de", "dos")))
    return " ".join(parts)


def fake_cpf(rng: random.Random, formatted: bool = True) -> str:
    base = _digits(rng, 9)
    digits = base + v.cpf_check_digits(base)
    return apply_format("000.000.000-00", digits) if formatted else digits


def fake_cnpj(rng: random.Random, formatted: bool = True, alphanumeric: bool = False) -> str:
    if alphanumeric:
        alphabet = "0123456789" + _LETTERS
        base = "".join(rng.choice(alphabet) for _ in range(8)) + "".join(rng.choice(alphabet) for _ in range(4))
        if base.isdigit():
            base = rng.choice(_LETTERS) + base[1:]
    else:
        base = _digits(rng, 8) + "0001"
    value = base + v.cnpj_check_digits(base)
    return apply_format("00.000.000/0000-00", value) if formatted else value


def fake_phone(rng: random.Random, style: str = "formatado", mobile: bool = True) -> str:
    ddd = rng.choice(sorted(v.VALID_DDDS))
    number = ("9" + rng.choice("6789") + _digits(rng, 7)) if mobile else (rng.choice("2345") + _digits(rng, 7))
    local = f"{number[:-4]}-{number[-4:]}"
    if style == "formatado":
        return f"({ddd}) {local}"
    if style == "internacional":
        return f"+55 {ddd} {local}"
    if style == "espacos":
        return f"{ddd} {number[:-4]} {number[-4:]}"
    return f"{ddd}{number}"


def fake_email(rng: random.Random, name: str | None = None, domain: str | None = None) -> str:
    words = re.sub(r"[^a-z ]", "", fold(name or fake_name(rng))).split()
    words = [word for word in words if word not in ("da", "de", "do", "das", "dos", "e")] or ["contato"]
    separator = rng.choice((".", "_", ""))
    local = separator.join((words[0], words[-1])) if len(words) > 1 else words[0]
    if rng.random() < 0.3:
        local += str(rng.randint(1, 99))
    # Domínios reservados para exemplos (RFC 2606): o e-mail inventado nunca é de alguém de verdade.
    domain = domain or rng.choice(("example.com", "example.org", "example.net", "empresa.example"))
    return f"{local}@{domain}"


def fake_cep(rng: random.Random, formatted: bool = True) -> str:
    digits = str(rng.randint(1, 9)) + _digits(rng, 7)
    return apply_format("00000-000", digits) if formatted else digits


def fake_plate(rng: random.Random, mercosul: bool = True) -> str:
    letters = "".join(rng.choice(_LETTERS) for _ in range(3))
    if mercosul:
        return f"{letters}{rng.randint(0, 9)}{rng.choice(_LETTERS)}{_digits(rng, 2)}"
    return f"{letters}-{_digits(rng, 4)}"


def fake_card(rng: random.Random, formatted: bool = True, first: str | None = None, length: int = 16) -> str:
    prefix = first or rng.choice(("4", "5"))
    body = prefix + _digits(rng, length - len(prefix) - 1)
    for check in "0123456789":
        if v.is_valid_luhn(body + check):
            number = body + check
            break
    if not formatted or length != 16:
        return number
    return " ".join(number[i:i + 4] for i in range(0, 16, 4))


def fake_pis(rng: random.Random, formatted: bool = True) -> str:
    base = _digits(rng, 10)
    digits = base + v.pis_check_digit(base)
    return apply_format("000.00000.00-0", digits) if formatted else digits


def fake_cns(rng: random.Random, formatted: bool = True) -> str:
    while True:
        base = rng.choice("12") + _digits(rng, 10) + "000"
        total = sum(int(char) * weight for char, weight in zip(base, range(15, 1, -1), strict=True))
        # O último dígito (peso 1) completa a soma até um múltiplo de 11.
        last = (11 - total % 11) % 11
        if last < 10:
            digits = base + str(last)
            break
    return apply_format("000 0000 0000 0000", digits) if formatted else digits


def fake_cnh(rng: random.Random) -> str:
    base = _digits(rng, 9)
    return base + v.cnh_check_digits(base)


def fake_titulo(rng: random.Random, formatted: bool = True) -> str:
    base = _digits(rng, 8) + f"{rng.randint(1, 28):02d}"
    digits = base + v.titulo_check_digits(base)
    return apply_format("0000 0000 0000", digits) if formatted else digits


def fake_renavam(rng: random.Random) -> str:
    base = _digits(rng, 10)
    return base + v.renavam_check_digit(base)


def fake_rg(rng: random.Random, formatted: bool = True) -> str:
    digits = _digits(rng, 8) + rng.choice("0123456789X")
    return apply_format("00.000.000-0", digits) if formatted else digits


def fake_passport(rng: random.Random) -> str:
    return "".join(rng.choice(_LETTERS) for _ in range(2)) + _digits(rng, 6)


def fake_pix_key(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def fake_ipv4(rng: random.Random) -> str:
    # Faixas reservadas para documentação (RFC 5737): não pertencem a ninguém.
    return f"{rng.choice(('192.0.2', '198.51.100', '203.0.113'))}.{rng.randint(1, 254)}"


def fake_ipv6(rng: random.Random) -> str:
    return f"2001:db8:{rng.randint(0, 0xffff):x}:{rng.randint(0, 0xffff):x}::{rng.randint(1, 0xffff):x}"


def fake_birthdate(rng: random.Random, style: str = "barras") -> str:
    day = date(1940, 1, 1) + timedelta(days=rng.randint(0, 365 * 65))
    if style == "extenso":
        return f"{day.day} de {_MONTH_NAMES[day.month - 1]} de {day.year}"
    if style == "iso":
        return day.isoformat()
    return day.strftime("%d/%m/%Y")


def fake_account(rng: random.Random) -> str:
    return f"{_digits(rng, rng.randint(5, 8))}-{rng.randint(0, 9)}"


def fake_processo(rng: random.Random) -> str:
    number, year = _digits(rng, 7), str(rng.randint(2005, 2026))
    segment, court, origin = rng.choice("458"), f"{rng.randint(1, 27):02d}", _digits(rng, 4)
    check = v.cnj_check_digits(number, year, segment, court, origin)
    return f"{number}-{check}.{year}.{segment}.{court}.{origin}"


def fake_address(rng: random.Random, street_type: str | None = None, number: bool = True) -> str:
    family = surnames()
    street = f"{street_type or rng.choice(_STREET_TYPES)} {rng.choice(first_names())} {rng.choice(family)}"
    return f"{street}, {rng.randint(1, 3999)}" if number else street


def _match_case(template: str, value: str) -> str:
    if template.isupper():
        return value.upper()
    if template.islower():
        return value.lower()
    return value


def make_surrogate(label: str, original: str, rng: random.Random) -> str | None:
    """Substituto do mesmo tipo e no mesmo formato do original, ou None se não houver gerador."""
    digits = only_digits(original)
    if label == "PESSOA":
        words = [w for w in original.split() if fold(w) not in ("da", "de", "do", "das", "dos", "e")]
        name = fake_name(rng, words=min(max(len(words), 1), 3))
        if len(words) == 1:
            name = name.split()[0]
        return _match_case(original, name)
    if label == "CPF" and len(digits) == 11:
        return apply_format(original, only_digits(fake_cpf(rng, formatted=False)))
    if label == "CNPJ" and len(v.normalize_cnpj(original)) == 14:
        return apply_format(original, fake_cnpj(rng, formatted=False))
    if label == "TELEFONE":
        local = v.phone_digits(original)
        if len(local) not in (10, 11):
            return None
        new = only_digits(fake_phone(rng, "digitos", mobile=len(local) == 11))
        return apply_format(original, digits[: len(digits) - len(local)] + new)
    if label == "EMAIL" and "@" in original:
        return fake_email(rng)
    if label == "CEP" and len(digits) == 8:
        return apply_format(original, only_digits(fake_cep(rng)))
    if label == "PLACA":
        compact = re.sub(r"[^0-9A-Za-z]", "", original)
        return fake_plate(rng, mercosul=bool(re.fullmatch(r"[A-Za-z]{3}\d[A-Za-z]\d{2}", compact))) \
            if "-" not in original else fake_plate(rng, mercosul=False)
    if label == "CARTAO_CREDITO" and 13 <= len(digits) <= 19:
        return apply_format(original, only_digits(fake_card(rng, formatted=False, first=digits[0], length=len(digits))))
    generators = {
        "PIS": (11, lambda: only_digits(fake_pis(rng))),
        "CNS": (15, lambda: only_digits(fake_cns(rng))),
        "CNH": (11, lambda: fake_cnh(rng)),
        "TITULO_ELEITOR": (12, lambda: only_digits(fake_titulo(rng))),
        "RENAVAM": (11, lambda: fake_renavam(rng)),
        "PROCESSO": (20, lambda: only_digits(fake_processo(rng))),
    }
    if label in generators:
        size, generate = generators[label]
        return apply_format(original, generate()) if len(digits) == size else apply_format(original, _digits(rng, len(digits)))
    if label in ("RG", "CONTA_BANCARIA"):
        return apply_format(original, "".join(rng.choice("0123456789") for _ in original if _.isalnum()))
    if label == "PASSAPORTE":
        return fake_passport(rng)
    if label == "CHAVE_PIX":
        return fake_pix_key(rng)
    if label == "IP":
        return fake_ipv6(rng) if ":" in original else fake_ipv4(rng)
    if label == "DATA_NASCIMENTO":
        if " de " in original:
            return fake_birthdate(rng, "extenso")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", original):
            return fake_birthdate(rng, "iso")
        return fake_birthdate(rng)
    if label == "ENDERECO":
        street_type = original.split()[0] if original.split() else None
        return fake_address(rng, street_type=street_type, number=bool(re.search(r"\d", original)))
    return None
