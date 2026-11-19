"""O nome da coluna é o contexto da célula: achado da simulação de ponta a ponta (scripts/simular_ponta_a_ponta.py)."""

import datetime
import json

import pytest

from veu import Veu
from veu.files import DataAnonymizer, anonymize_file, anonymize_text, restore_file


@pytest.mark.parametrize(
    "key,value,label",
    [
        ("nascimento", "11/01/1941", "DATA_NASCIMENTO"),
        ("data_nascimento", "11/01/1941", "DATA_NASCIMENTO"),
        ("dataNascimento", "1941-01-11", "DATA_NASCIMENTO"),
        ("birth_date", "1941-01-11", "DATA_NASCIMENTO"),
        ("nome", "Ana", "PESSOA"),
        ("cpfCliente", "52998224725", "CPF"),
    ],
)
def test_column_name_is_the_context_of_the_cell(key, value, label):
    session = Veu().session()
    assert session.anonymize(value, context=key) == f"[{label}_1]"
    assert session.anonymize(value) in (value, f"[{label}_1]")  # sem o contexto, nada garante a detecção


def test_csv_and_json_cells_use_their_columns():
    csv_text = "nome;data_nascimento;cargo\nAna Lima;11/01/1941;Analista\n"
    data = DataAnonymizer(Veu().session())
    output = anonymize_text(csv_text, "csv", data)
    assert "11/01/1941" not in output and "Ana Lima" not in output and "Analista" in output
    parsed = json.loads(anonymize_text(json.dumps([{"dt_nasc": "11/01/1941", "salario": 4200}]), "json", data))
    assert parsed == [{"dt_nasc": "[DATA_NASCIMENTO_1]", "salario": 4200}]


def test_typed_excel_cells_are_protected_and_restored_as_text(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["nome", "cpf", "telefone", "nascimento", "salario", "admissao"])
    sheet.append(["Ana", 52998224725, 11987654321, datetime.datetime(1985, 4, 3), 4200, datetime.datetime(2020, 1, 15)])
    book.save(tmp_path / "a.xlsx")
    vault, _ = anonymize_file(tmp_path / "a.xlsx", tmp_path / "b.xlsx")
    row = [cell.value for cell in openpyxl.load_workbook(tmp_path / "b.xlsx").active[2]]
    assert row[:4] == ["[PESSOA_1]", "[CPF_1]", "[TELEFONE_1]", "[DATA_NASCIMENTO_1]"]
    assert row[4] == 4200 and row[5] == datetime.datetime(2020, 1, 15)
    restore_file(tmp_path / "b.xlsx", tmp_path / "c.xlsx", vault)
    restored = [cell.value for cell in openpyxl.load_workbook(tmp_path / "c.xlsx").active[2]]
    assert restored[:4] == ["Ana", "52998224725", "11987654321", "03/04/1985"]
