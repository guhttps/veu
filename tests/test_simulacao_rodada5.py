"""Achados da quinta rodada da simulação de uso (scripts/simular_usuarios.py)."""

import pytest

from veu import Veu


@pytest.mark.parametrize("text,place", [
    ("Sou o Rui Porto, moro na Rua de Santa Catarina, 120, 4050-262 Porto.", "4050-262 Porto"),
    ("A cliente Ana Campos mora em Campos/RJ.", "Campos/RJ"),
    ("A cliente Ana Campos mora em Campos - RJ.", "Campos - RJ"),
    ("O réu é João Lima, da comarca de Lima.", "comarca de Lima"),
])
def test_surname_that_is_also_a_city_keeps_the_city(text, place):
    """O sobrenome "Porto" ligava a cidade do endereço à pessoa, e a volta punha o nome inteiro no lugar da cidade."""
    result = Veu().anonymize(text)
    assert place in result.text
    assert result.restore(result.text) == text


def test_later_mentions_of_the_surname_are_still_hidden():
    result = Veu().anonymize("A cliente Ana Campos mora em Campos/RJ. A Campos pediu retorno.")
    assert result.text.endswith("A [PESSOA_1] pediu retorno.")
