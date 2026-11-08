"""Nomes: listas do Censo 2022 do IBGE, propagação de nomes confirmados e o que não é pessoa."""

import pytest

from veu import Veu
from veu.recognizers.base import load_wordlist

veu = Veu()


def people(text):
    return [entity.text for entity in veu.analyze(text) if entity.label == "PESSOA"]


@pytest.mark.parametrize("text, name", [
    # Nomes comuns em quem nasceu depois de 2000, que as listas curadas não tinham.
    ("O responsável pela análise é Anthony Raul Viana.", "Anthony Raul Viana"),
    ("Contratado(a): Isabelle Melissa Assis, brasileira.", "Isabelle Melissa Assis"),
    ("Cliente: Kamilly Hadassa Carvalho", "Kamilly Hadassa Carvalho"),
    # Sobrenome que também é prenome raro não corta o nome ("Kawanny Rodrigues" não vira "Rodrigues").
    ("Meu nome é Kawanny Rodrigues e moro em Natal.", "Kawanny Rodrigues"),
])
def test_ibge_first_names(text, name):
    assert name in people(text)


@pytest.mark.parametrize("text", [
    "Endereço: Avenida Paulista, 1578.",          # logradouro, mesmo com "Paulista" na lista de sobrenomes
    "O evento será em São Cristóvão.",             # santo ou lugar
    "Moro em Santa Maria e trabalho em Belo Jardim.",
    "Razão Social: Exemplo Ltda",                  # rótulo de formulário
    "Certidão de Nascimento",
])
def test_not_people(text):
    assert people(text) == []


def test_towns_that_start_with_a_first_name_are_not_places():
    """"Paulo Afonso" é município, mas também pode ser uma pessoa: tem de continuar sendo escondido."""
    towns = set(load_wordlist("ibge_municipios.txt"))
    assert "Belo Jardim" in towns and "Paulo Afonso" not in towns and "Carlos Barbosa" not in towns
    assert "Paulo Afonso" in people("O cliente Paulo Afonso ligou.")


def test_ambiguous_names_come_from_the_dictionary():
    ambiguous = set(load_wordlist("ibge_ambiguos.txt"))
    assert {"rosa", "natal", "gloria", "flor"} <= ambiguous
    assert not {"kamilly", "anthony", "enzo", "maria"} & ambiguous


@pytest.mark.parametrize("text, expected", [
    ("Oi, sou a Rayane Souza. kkkk a rayane esqueceu o carregador. RAYANE SOUZA assinou.",
     "Oi, sou a [PESSOA_1]. kkkk a [PESSOA_1] esqueceu o carregador. [PESSOA_1] assinou."),
    ("O José Carlos ligou; depois o jose voltou.", "O [PESSOA_1] ligou; depois o [PESSOA_1] voltou."),
    ("Oi Kamilly! ... a kamilly vem amanhã", "Oi [PESSOA_1]! ... a [PESSOA_1] vem amanhã"),
    # Nome ambíguo não se propaga para a palavra comum.
    ("Rosa Pereira ligou. A rosa do jardim murchou.", "[PESSOA_1] ligou. A rosa do jardim murchou."),
    # Só palavras inteiras.
    ("A Rayane Souza falou com a rayanesouza do suporte.", "A [PESSOA_1] falou com a rayanesouza do suporte."),
])
def test_confirmed_names_propagate(text, expected):
    assert veu.anonymize(text).text == expected


def test_propagation_can_be_turned_off():
    text = "Oi, sou a Rayane Souza. kkkk a rayane esqueceu."
    assert "rayane" in Veu(link_names=False).anonymize(text).text
