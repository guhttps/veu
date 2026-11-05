import random

import pytest

from veu import surrogates as fake
from veu import validators as v


@pytest.mark.parametrize("value", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_valid_cpfs(value):
    assert v.is_valid_cpf(value)


@pytest.mark.parametrize("value", ["529.982.247-26", "111.111.111-11", "123", "000.000.000-00"])
def test_invalid_cpfs(value):
    assert not v.is_valid_cpf(value)


def test_cnpj_numeric_and_alphanumeric():
    assert v.is_valid_cnpj("11.222.333/0001-81")
    # Exemplo oficial da Receita Federal para o CNPJ alfanumérico (julho de 2026).
    assert v.is_valid_cnpj("12.ABC.345/01DE-35")
    assert v.is_valid_cnpj("12ABC34501DE35")
    assert not v.is_valid_cnpj("12.ABC.345/01DE-36")
    assert not v.is_valid_cnpj("00.000.000/0000-00")


def test_card_requires_luhn_and_known_prefix():
    assert v.is_valid_card("4111 1111 1111 1111")
    assert not v.is_valid_card("4111 1111 1111 1112")
    assert not v.is_valid_card("1111 1111 1111 1117")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("(11) 91234-5678", True), ("+55 21 3456-7890", True), ("11912345678", True), ("(20) 91234-5678", False),
     ("(11) 81234-5678", False), ("(11) 1234-5678", False)],
)
def test_phones(value, expected):
    assert v.is_valid_phone(value) is expected


def test_processo_cnj_check_digits():
    rng = random.Random(3)
    for _ in range(20):
        assert v.is_valid_processo_cnj(fake.fake_processo(rng))
    assert not v.is_valid_processo_cnj("0000000-00.2020.8.26.0000")


def test_birthdates():
    assert v.is_plausible_birthdate("12/03/1990")
    assert v.is_plausible_birthdate("5 de março de 1987")
    assert v.is_plausible_birthdate("1990-03-12")
    assert not v.is_plausible_birthdate("31/02/1990")
    assert not v.is_plausible_birthdate("12/03/2999")


def test_ips():
    assert v.is_valid_ipv4("200.147.67.142")
    assert not v.is_valid_ipv4("127.0.0.1")
    assert not v.is_valid_ipv4("300.1.1.1")
    assert v.is_valid_ipv6("2804:14c:5b:a0::1")
    assert not v.is_valid_ipv6("10:30:00")


@pytest.mark.parametrize(
    ("generator", "validator"),
    [
        (lambda r: fake.fake_cpf(r), v.is_valid_cpf),
        (lambda r: fake.fake_cnpj(r), v.is_valid_cnpj),
        (lambda r: fake.fake_cnpj(r, alphanumeric=True), v.is_valid_cnpj),
        (lambda r: fake.fake_pis(r), v.is_valid_pis),
        (lambda r: fake.fake_cns(r), v.is_valid_cns),
        (lambda r: fake.fake_cnh(r), v.is_valid_cnh),
        (lambda r: fake.fake_titulo(r), v.is_valid_titulo_eleitor),
        (lambda r: fake.fake_renavam(r), v.is_valid_renavam),
        (lambda r: fake.fake_card(r), v.is_valid_luhn),
        (lambda r: fake.fake_phone(r), v.is_valid_phone),
    ],
)
def test_generated_documents_are_valid(generator, validator):
    rng = random.Random(42)
    for _ in range(200):
        assert validator(generator(rng))
