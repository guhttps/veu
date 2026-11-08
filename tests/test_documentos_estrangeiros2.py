"""Documentos da África lusófona, dos EUA, da Europa e da Índia, passaportes (MRZ), chassi e carteiras de criptomoeda.

Os números são os exemplos sintéticos das especificações (e da documentação do python-stdnum 2.2), não de pessoas.
"""

import re

import pytest

from veu import Veu
from veu import validators as v
from veu.bench.generator import generate
from veu.recognizers import patterns

veu = Veu()

MRZ_NAME = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
MRZ_LINE = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def labels(text):
    return [(entity.label, entity.text) for entity in veu.analyze(text)]


@pytest.mark.parametrize("validator, valid, invalid", [
    (v.is_valid_nuit, ["123 456 785", "123456785"], ["123 456 784", "12345678"]),
    (v.is_valid_ssn, ["123-45-6789", "900-70-1234"], ["000-12-3456", "666-12-3456", "123-00-4567", "123-45-0000",
                                                      "078-05-1120", "900-89-1234", "900-12-3456"]),
    (v.is_valid_dni_es, ["12345678Z", "X1234567L", "y1234567x"], ["12345678A", "X12345678L", "1234567Z"]),
    (v.is_valid_codice_fiscale, ["RSSMRA80A01H501U"], ["RSSMRA80A01H501V", "RSSMRA80Z01H501U"]),
    (v.is_valid_nir, ["1 80 01 75 123 456 60", "1 80 01 2A 123 456 20"], ["1 80 01 75 123 456 61", "3 80 01 75 123 456 60"]),
    (v.is_valid_steuer_id, ["12345678911"], ["12345678912", "02345678911", "12345678901"]),
    (v.is_valid_nino, ["AB 12 34 56 C", "AB123456"], ["BG123456C", "DA123456C", "AO123456C", "AB123456E"]),
    (v.is_valid_nhs, ["999 000 0018"], ["999 000 0019", "999 000 001"]),
    (v.is_valid_bsn, ["123456782", "111222333"], ["123456781", "000000000"]),
    (v.is_valid_sin, ["123 456 782"], ["123 456 781", "023 456 782", "823 456 782"]),
    (v.is_valid_aadhaar, ["2345 6789 0124"], ["2345 6789 0125", "1345 6789 0124"]),
    (v.is_valid_mrz_line, [MRZ_LINE], [MRZ_LINE[:9] + "7" + MRZ_LINE[10:], MRZ_LINE[:43] + "1"]),
    (v.is_valid_vin, ["1M8GDM9AXKP042788"], ["1M8GDM9AXKP042789", "11111111111111111", "1M8GDM9AIKP042788"]),
    (v.is_valid_crypto_address, ["0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                                 "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"],
     ["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdp", "0x5aAeb6053F3E94C9b9A09f3366"]),
])
def test_check_digits(validator, valid, invalid):
    assert all(validator(value) for value in valid)
    assert not any(validator(value) for value in invalid)


@pytest.mark.parametrize("text, expected", [
    # Formatos próprios: valem sem contexto.
    ("o número 123-45-6789 está no formulário", ("SSN", "123-45-6789")),
    ("documento 12345678Z", ("DNI_ES", "12345678Z")),
    ("residente X1234567L", ("DNI_ES", "X1234567L")),
    ("RSSMRA80A01H501U", ("CODICE_FISCALE", "RSSMRA80A01H501U")),
    ("número 1 80 01 75 123 456 60", ("NIR", "1 80 01 75 123 456 60")),
    ("AB 12 34 56 C", ("NINO", "AB 12 34 56 C")),
    ("BI 123456789LA123", ("BI_AO", "123456789LA123")),
    (MRZ_LINE, ("MRZ", MRZ_LINE)),
    (MRZ_NAME, ("MRZ", MRZ_NAME)),
    ("o carro 1M8GDM9AXKP042788 foi vendido", ("VIN", "1M8GDM9AXKP042788")),
    ("envie para 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", ("CRIPTO", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")),
    ("envie para 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", ("CRIPTO", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")),
    # Números puros: só com contexto.
    ("NUIT 123 456 785", ("NUIT", "123 456 785")),
    ("SSN: 123456789", ("SSN", "123456789")),
    ("Medicare MBI 1EG4-TE5-MK73", ("MBI", "1EG4-TE5-MK73")),
    ("Steuer-ID 12345678911", ("STEUER_ID", "12345678911")),
    ("NHS number 999 000 0018", ("NHS", "999 000 0018")),
    ("BSN 123456782", ("BSN", "123456782")),
    ("SIN 123 456 782", ("SIN", "123 456 782")),
    ("Aadhaar 2345 6789 0124", ("AADHAAR", "2345 6789 0124")),
    ("PAN ABCPD1234E", ("PAN", "ABCPD1234E")),
    ("NIR 180017512345660", ("NIR", "180017512345660")),
    ("BI nº 123456789012A", ("BI_MZ", "123456789012A")),
    ("chassi 9BWZZZ377VT004251", ("VIN", "9BWZZZ377VT004251")),
])
def test_detected(text, expected):
    assert expected in labels(text)


@pytest.mark.parametrize("text", [
    "pedido 123456782 entregue",                 # BSN e SIN válidos, mas sem contexto
    "o código ABCPD1234E do produto",            # formato do PAN, sem contexto
    "lote 1M8GDM9AXKP042789",                    # VIN com dígito errado e sem contexto
    "notAfter 261108123045Z",                    # data de certificado X.509, não BI de Moçambique
    "a nota 20231108A",                          # 8 dígitos e uma letra que não fecha o DNI
    "entregue nas lojas 123 456 782",            # "nas" não é contexto do SIN
    "uid 2345 6789 0124 do processo",            # "uid" sozinho não é contexto do Aadhaar
    "hash 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "carteira 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb",  # Base58Check que não confere
])
def test_not_detected_without_context_or_check(text):
    new = {"NUIT", "BI_AO", "BI_MZ", "SSN", "MBI", "DNI_ES", "CODICE_FISCALE", "NIR", "STEUER_ID", "NINO", "NHS", "BSN",
           "SIN", "AADHAAR", "PAN", "MRZ", "VIN", "CRIPTO"}
    assert not [item for item in labels(text) if item[0] in new]


def test_vin_needs_letters_and_digits_even_with_context():
    assert not [item for item in labels("chassi 11111111111111111") if item[0] == "VIN"]


def test_round_trip_and_digit_markers():
    text = "SSN 123-45-6789, BSN 123456782, C.F. RSSMRA80A01H501U e carteira 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    result = veu.anonymize(text)
    assert "123-45-6789" not in result.text and "RSSMRA80A01H501U" not in result.text
    assert result.restore(result.text) == text


def test_brazilian_documents_still_win():
    # CPF formatado não vira SSN nem SIN; o CNPJ não vira nada estrangeiro.
    assert labels("CPF 529.982.247-25 e CNPJ 11.222.333/0001-81") == [("CPF", "529.982.247-25"),
                                                                      ("CNPJ", "11.222.333/0001-81")]


TRICKY = "\n".join([
    "x123-45-6789 _123-45-6789 a12345678Z 12345678Zb ÁRSSMRA80A01H501U AB 12 34 56 Cx",
    "9" * 30, "Z" * 30, MRZ_LINE + "<", "<" + MRZ_LINE, "1M8GDM9AXKP0427881", "é1M8GDM9AXKP042788",
    "CPF*529.982.***-** **529.982.247-25 9 1234-5678 2345-6789",
])


@pytest.mark.parametrize("spec", [spec for spec in patterns.DEFAULT_SPECS if patterns._class_first(spec.pattern) != spec.pattern],
                         ids=lambda spec: spec.label)
def test_class_first_rewrite_matches_the_same(spec):
    """A reescrita que acelera as expressões precisa casar exatamente as mesmas coisas que a original."""
    text = "\n".join(sample.text for sample in generate(150, seed=5)) + "\n" + TRICKY
    original = re.compile(spec.pattern, spec.flags)
    assert [m.span() for m in spec.compiled.finditer(text)] == [m.span() for m in original.finditer(text)]


def test_class_first_skips_optional_leading_tokens():
    assert patterns._class_first(patterns.B + r"[XYZ]?\d{7}") == patterns.B + r"[XYZ]?\d{7}"
    assert patterns._class_first(patterns.B + r"\d*x") == patterns.B + r"\d*x"
    assert patterns._class_first(patterns.B + r"\d{0,3}x") == patterns.B + r"\d{0,3}x"
    assert patterns._class_first(patterns.B + r"\d{3}x") == r"\d(?<![\w]\d)\d{2}x"
    assert patterns._class_first(patterns.B + r"\d{2,4}x") == r"\d(?<![\w]\d)\d{1,3}x"
    assert patterns._class_first(patterns.B + r"[a-z]+x") == r"[a-z](?<![\w][a-z])[a-z]*x"
