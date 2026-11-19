"""Listas próprias (plano Pro): termos que sempre são escondidos, sem ligar para maiúsculas e acentos."""

import pytest

from veu import Veu
from veu.config import Config, ConfigError
from veu.recognizers.terms import fold_keeping_positions

TERMS = {"PESSOA": ["Joana Prado"], "TERMO": ["Projeto Netuno", "Acme", "Açaí Bom"]}

# Os mesmos casos estão em js/test/listas.test.ts: as duas versões precisam concordar.
CASES = [
    ("A JOANA PRADO aprovou o projeto netuno.", "A [PESSOA_1] aprovou o [TERMO_1]."),
    ("Reunião do Projeto  Netuno com a Acme.", "Reunião do [TERMO_1] com a [TERMO_2]."),
    ("A AÇAI BOM chegou.", "A [TERMO_1] chegou."),
    ("Projeto Netunos, acmeo e banana ficam.", "Projeto Netunos, acmeo e banana ficam."),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_terms_ignore_case_accents_and_spacing_but_need_whole_words(text, expected):
    result = Veu(terms=TERMS).anonymize(text)
    assert result.text == expected
    assert result.restore(result.text) == text


def test_fold_keeps_positions():
    text = "Ação Ü ß İ x"
    assert len(fold_keeping_positions(text)) == len(text)
    assert fold_keeping_positions("ÁÉÍÓÚ Çç") == "aeiou cc"


def test_terms_from_veu_toml(tmp_path):
    from veu.config import load_config

    path = tmp_path / "veu.toml"
    path.write_text('[deteccao.termos]\nTERMO = ["Projeto Netuno"]\nPESSOA = ["Joana Prado"]\n', encoding="utf-8")
    config = load_config(path)
    assert Veu(config).anonymize("O Projeto Netuno da Joana Prado").text == "O [TERMO_1] da [PESSOA_1]"


def test_unknown_label_in_terms_is_an_error():
    with pytest.raises(ConfigError, match="INVENTADO"):
        Config(terms={"INVENTADO": ["x"]})


def test_without_terms_nothing_changes():
    assert Veu().anonymize("Projeto Netuno").text == "Projeto Netuno"
