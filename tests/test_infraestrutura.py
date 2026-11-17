"""Portas e nomes de servidores internos: só quando dá para ter certeza de que o número é uma porta."""

import pytest

from veu import Veu
from veu import validators as v

veu = Veu()


def found(text):
    return [(entity.label, entity.text) for entity in veu.analyze(text) if entity.label in ("PORTA", "SERVIDOR", "IP")]


@pytest.mark.parametrize("text, expected", [
    ("acesse 10.0.0.5:8080", [("IP", "10.0.0.5"), ("PORTA", "8080")]),
    ("IPv6 [2001:db8::1]:443", [("IP", "2001:db8::1"), ("PORTA", "443")]),
    ("o servidor atende na porta 5432", [("PORTA", "5432")]),
    ("Port: 3000", [("PORTA", "3000")]),
    ("PORT=8080", [("PORTA", "8080")]),
    ("DB_PORT=5432", [("PORTA", "5432")]),
    ('{"port": 6379}', [("PORTA", "6379")]),
    ("app --port 9000", [("PORTA", "9000")]),
    ("ssh -p 2222 usuario@servidor", [("PORTA", "2222")]),
    ("docker run -p 8080:80 nginx", [("PORTA", "8080"), ("PORTA", "80")]),
    ("abra https://api.empresa.example:8443/v1", [("PORTA", "8443")]),
    ("localhost:3000", [("PORTA", "3000")]),
    ("banco em db.interna:5432", [("SERVIDOR", "db.interna"), ("PORTA", "5432")]),
    ("cache em cache.prod.local e fila.corp", [("SERVIDOR", "cache.prod.local"), ("SERVIDOR", "fila.corp")]),
    ("o servidor fila.empresa.example:5672 responde", [("PORTA", "5672")]),
])
def test_detected(text, expected):
    assert found(text) == expected


@pytest.mark.parametrize("text", [
    "reunião às 10:30",
    "erro em app.py:120",              # arquivo e linha, não servidor e porta
    "apartamento 302 e sala 1204",
    "relatório 2024 e transporte 2025",
    "versão 1.2.3:45",
    "porta 65536",                     # acima do limite
    "porta 080",                       # zero à esquerda
    "a nota foi 8080",
    "db.interna.example",              # termina num domínio público
    "mysql -p",                        # -p sem número é a senha
    "pip install -p 3000",             # -p só vale em comandos de rede
])
def test_not_detected(text):
    assert not [item for item in found(text) if item[0] in ("PORTA", "SERVIDOR")]


def test_internal_host_in_an_email_is_the_email():
    assert [entity.label for entity in veu.analyze("fale com joao@empresa.local")] == ["EMAIL"]


def test_port_validator():
    assert all(v.is_valid_port(value) for value in ("1", "80", "65535"))
    assert not any(v.is_valid_port(value) for value in ("0", "080", "65536", "", "8a"))


def test_round_trip():
    text = "Conecte em db.interna:5432 (reserva: 10.0.0.9:5433)."
    result = veu.anonymize(text)
    assert result.text == "Conecte em [SERVIDOR_1]:[PORTA_1] (reserva: [IP_1]:[PORTA_2])."
    assert result.restore(result.text) == text


def test_can_be_turned_off():
    only_documents = Veu(labels=["CPF"])
    assert only_documents.anonymize("10.0.0.5:8080").text == "10.0.0.5:8080"


def test_every_label_is_in_exactly_one_checkbox_group():
    from veu.entities import LABELS, load_groups

    grouped = [label for group in load_groups() for label in group["tipos"]]
    assert sorted(grouped) == sorted(LABELS)  # nenhum tipo sem caixinha, nenhum repetido, nenhum inventado
    assert all(group["titulo"] and group["titulo_en"] and group["exemplo"] and group["exemplo_en"] for group in load_groups())
