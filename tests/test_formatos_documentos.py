"""Formatos de documentos que a avaliação externa mostrou faltar: mascarados pela metade, com espaços e com hífen."""

import pytest

from veu import Veu

veu = Veu()


def labels(text):
    return [(entity.label, entity.text) for entity in veu.analyze(text)]


@pytest.mark.parametrize("text, expected", [
    # Mascarados pela metade: os dígitos que sobram ainda identificam a pessoa.
    ("CPF: 529.982.***-**", ("CPF", "529.982.***-**")),
    ("Servidor ***.982.247-** no portal", ("CPF", "***.982.247-**")),
    ("CPF 529.982.XXX-XX", ("CPF", "529.982.XXX-XX")),
    ("CNPJ 11.222.333/****-**", ("CNPJ", "11.222.333/****-**")),
    ("RG nº 12.34***-*", ("RG", "12.34***-*")),
    ("CNH nº 02650******", ("CNH", "02650******")),
    ("Título de Eleitor nº 1023****0191", ("TITULO_ELEITOR", "1023****0191")),
    # Com espaços ou hífen
    ("Fornecedor CNPJ 11 222 333 0001 81", ("CNPJ", "11 222 333 0001 81")),
    ("RG nº 12 345 678 9", ("RG", "12 345 678 9")),
    ("CNH 0265030646-1", ("CNH", "0265030646-1")),
    ("CEP 01310 100", ("CEP", "01310 100")),
])
def test_new_formats(text, expected):
    assert expected in labels(text)


@pytest.mark.parametrize("text", [
    "o campo ***.***.***-** veio vazio",       # sem dígitos: nada a esconder
    "a senha tem 8 caracteres: ********",
    "11 222 333 0001 82",                      # CNPJ com dígito errado
    "código 01310 100",                        # CEP com espaço só com contexto
])
def test_no_false_positives(text):
    found = labels(text)
    assert found == []


def test_partially_masked_values_are_hidden():
    result = veu.anonymize("Cliente CPF 529.982.***-**, CNPJ 11.222.333/****-**")
    assert result.text == "Cliente CPF [CPF_1], CNPJ [CNPJ_1]"
