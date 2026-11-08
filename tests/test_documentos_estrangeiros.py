"""Documentos de Portugal e da América Latina: dígitos verificadores, níveis de confiança e colisões com o Brasil.

Os números são sintéticos (sequências como 12345678) e foram conferidos com o python-stdnum 2.2.
"""

import pytest

from veu import Veu
from veu import validators as v

veu = Veu()


def labels(text):
    return [(entity.label, entity.text) for entity in veu.analyze(text)]


@pytest.mark.parametrize("validator, valid, invalid", [
    (v.is_valid_nif_pt, ["123456789", "500000000"], ["123456788", "823456789"]),
    (v.is_valid_cc_pt, ["12345678 9 ZZ1", "000000000ZZ4"], ["12345678 9 ZZ2"]),
    (v.is_valid_niss_pt, ["11234567892"], ["11234567893", "31234567892"]),
    (v.is_valid_cuit, ["20-12345678-6", "30-12345678-1"], ["20-12345678-5", "40-12345678-6"]),
    (v.is_valid_curp, ["XAXX900101HDFXXX03"], ["XAXX900101HDFXXX04", "XAXX901301HDFXXX03", "XAXX900101HZZXXX03"]),
    (v.is_valid_rfc, ["PEPJ900101AB8", "ABC010101AB1"], ["XAXX010101000", "PEPJ901301AB8"]),
    (v.is_valid_rut_cl, ["12.345.678-5", "11.111.111-1", "7.654.321-6"], ["12.345.678-4"]),
    (v.is_valid_rut_uy, ["211234560019"], ["211234560018", "231234560019"]),
    (v.is_valid_ci_uy, ["1.234.567-2"], ["1.234.567-3"]),
    (v.is_valid_ci_ec, ["1712345675"], ["1712345674", "2712345675"]),
    (v.is_valid_nit_co, ["900.123.456-8"], ["900.123.456-7"]),
    (v.is_valid_ruc_pe, ["20123456786", "10123456781"], ["20123456787", "30123456786"]),
    (v.is_valid_ruc_py, ["1234567-9", "80012345-0"], ["1234567-8"]),
    (v.is_valid_rif, ["V-12345678-1", "J-12345678-4"], ["V-12345678-2", "X-12345678-1"]),
])
def test_check_digits(validator, valid, invalid):
    assert all(validator(value) for value in valid)
    assert not any(validator(value) for value in invalid)


@pytest.mark.parametrize("text, expected", [
    # Formatos estruturados ou com a pontuação típica: sem contexto.
    ("Cartão 12345678 9 ZZ1 renovado", ("CC_PT", "12345678 9 ZZ1")),
    ("Contribuinte argentino 20-12345678-6", ("CUIT", "20-12345678-6")),
    ("Cliente XAXX900101HDFXXX03 cadastrado", ("CURP", "XAXX900101HDFXXX03")),
    ("Fatura para PEPJ900101AB8", ("RFC", "PEPJ900101AB8")),
    ("Fornecedor J-12345678-4", ("RIF", "J-12345678-4")),
    ("Proveedor 900.123.456-8", ("NIT", "900.123.456-8")),
    # Só com contexto.
    ("NIF: 123 456 789", ("NIF_PT", "123 456 789")),
    ("NISS 11234567892", ("NISS_PT", "11234567892")),
    ("CUIL 20123456786", ("CUIT", "20123456786")),
    ("D.N.I. 12.345.678", ("DNI", "12.345.678")),
    ("RUT: 12.345.678-5", ("RUT", "12.345.678-5")),
    ("RUT 211234560019", ("RUT", "211234560019")),
    ("Cédula de identidad 1.234.567-2", ("CEDULA", "1.234.567-2")),
    ("cédula 1712345675", ("CEDULA", "1712345675")),
    ("RUC 20123456786", ("RUC", "20123456786")),
    ("RUC 1234567-9", ("RUC", "1234567-9")),
])
def test_detection(text, expected):
    assert expected in labels(text)


@pytest.mark.parametrize("text", [
    "pedido 123456789 enviado",              # 9 dígitos soltos: não vira NIF
    "o número 20123456786 é",                # 11 dígitos soltos sem contexto: não vira CUIT nem RUC
    "protocolo 202569473616",                # 12 dígitos: não vira Cartão de Cidadão
    "código ABCD900101XYZ1 do produto",      # parece RFC, mas tem um caractere a mais
    "o RFC genérico XAXX010101000",          # "público em geral", não é uma pessoa
])
def test_no_false_positives(text):
    assert labels(text) == []


def test_brazil_wins_ambiguous_formats():
    """Sem contexto, formatos que existem nos dois lados ficam com o rótulo brasileiro (o público principal)."""
    assert labels("RG 12.345.678-5") == [("RG", "12.345.678-5")]
    assert labels("CPF 529.982.247-25") == [("CPF", "529.982.247-25")]
    # Com contexto do outro país, o rótulo dele vence o CPF de 11 dígitos.
    assert labels("CUIT 20123456786") == [("CUIT", "20123456786")]
    assert labels("NISS 11234567892") == [("NISS_PT", "11234567892")]


def test_anonymize_and_restore():
    text = "Contrato com J-12345678-4 e o cliente XAXX900101HDFXXX03, NIF: 123 456 789."
    result = veu.anonymize(text)
    assert result.text == "Contrato com [RIF_1] e o cliente [CURP_1], NIF: [NIF_PT_1]."
    assert result.restore(result.text) == text
