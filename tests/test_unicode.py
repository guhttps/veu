"""Normalização para a detecção: caracteres invisíveis, hífens tipográficos e largura total não escondem dados."""

import pytest

from veu import Veu
from veu.analyzer import normalize_for_detection

veu = Veu()
KEY = "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d"


@pytest.mark.parametrize("text, label", [
    ("CPF 529.982.247‑25", "CPF"),                                  # hífen inseparável (Word)
    ("CPF 529.982.247−25", "CPF"),                                  # sinal de menos
    ("CPF ５２９.９８２.２４７-２５", "CPF"),  # largura total
    (f"chave {KEY[:3]}​{KEY[3:]}", "CHAVE_API"),                     # largura zero no meio da chave
    ("e-mail maria­.souza@example.com", "EMAIL"),                    # hífen invisível
    ("tel (11) 98765‑4321", "TELEFONE"),
])
def test_hidden_characters_do_not_hide_data(text, label):
    entities = veu.analyze(text)
    assert [entity.label for entity in entities] == [label]
    entity = entities[0]
    assert text[entity.start:entity.end] == entity.text  # posições no texto original
    assert veu.anonymize(text).restore(veu.anonymize(text).text) == text


def test_plain_text_is_not_copied():
    text = "CPF 529.982.247-25"
    assert normalize_for_detection(text) == (text, None)


def test_dashes_in_prose_stay():
    assert veu.anonymize("Relatório 2020–2021 — versão final").text == "Relatório 2020–2021 — versão final"
