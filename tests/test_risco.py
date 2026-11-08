"""Risco de identificação pelo contexto e o operador generalizar."""

import json

from veu import Veu
from veu.cli import main
from veu.risk import assess


def test_quasi_identifiers_raise_the_risk():
    text = "A [PESSOA_1], gerente de 45 anos da filial de Itu, foi demitida em 12/03/2026."
    report = assess(text)
    assert report.level == "alto" and set(report.quasi) == {"CARGO", "IDADE", "CIDADE", "DATA"}
    assert not report.direct


def test_direct_identifiers_are_high_risk():
    report = assess("Cliente Maria Souza, CPF 529.982.247-25")
    assert report.level == "alto" and report.direct["CPF"] == 1


def test_levels():
    assert assess("O relatório trimestral foi aprovado.").level == "baixo"
    assert assess("A reunião foi em 3 de maio de 2026.").level == "médio"


def test_cli(tmp_path, capsys):
    path = tmp_path / "texto.txt"
    path.write_text("O [PESSOA_1], professor de 52 anos em Santos, saiu em março de 2025.", encoding="utf-8")
    assert main(["risco", str(path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["nivel"] == "alto" and data["quase_identificadores"]["IDADE"] == 1


def test_generalize_operator():
    text = ("Maria Souza, nascida em 7 de setembro de 1985, CEP 01310-100, tel (11) 98765-4321, +44 20 7946 0958, "
            "IP 192.0.2.44, CPF 529.982.247-25")
    result = Veu(operator="generalizar").anonymize(text).text
    assert result == ("[PESSOA], nascida em 1985, CEP 01310-***, tel (11) ****-****, +44 ****, IP 192.0.2.0/24, "
                      "CPF [CPF]")
    assert len(Veu(operator="generalizar").anonymize(text).vault) == 0  # nada a restaurar
