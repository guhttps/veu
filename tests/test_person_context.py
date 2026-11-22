"""Contexto de nomes: a palavra de contexto vale na mesma linha, ou no rótulo que fecha a linha de cima."""

import pytest

from veu import Veu


@pytest.mark.parametrize(
    "text",
    [
        "Para: Thiago Lima\nChave Pix: (82) 98501-3510",
        "Para: Thiago Lima\nForma Pagamento: Boleto",
        "De: Jefferson Figueiredo\nAssunto: Proposta Comercial",
        "Comprovante de transferência Pix\nDe: Altair Batista Linhares",
    ],
)
def test_context_from_the_line_above_does_not_create_names(text):
    # Achado da simulação de uso: num comprovante Pix, "Para: Fulano" fazia de "Chave Pix:" um nome.
    names = [entity.text for entity in Veu().anonymize(text).entities if entity.label == "PESSOA"]
    assert all("Pix" not in name and "Pagamento" not in name and "Proposta" not in name for name in names)
    assert len(names) == 1


@pytest.mark.parametrize("text,name", [("Nome:\nMaria Souza", "Maria Souza"), ("Cliente:\nJoão Pedro Alves", "João Pedro Alves")])
def test_label_closing_the_line_above_still_counts(text, name):
    assert [entity.text for entity in Veu().anonymize(text).entities] == [name]


def _pessoas(text: str) -> list[str]:
    return [entity.text for entity in Veu().analyze(text) if entity.label == "PESSOA"]


@pytest.mark.parametrize(("text", "names"), [
    # Prenome sozinho em minúsculas depois de artigo, preposição ou tratamento.
    ("liga pro pedro e avisa que a reunião mudou", ["pedro"]),
    ("o joão paulo falou que a fernanda vai cobrir o turno", ["joão paulo", "fernanda"]),
    ("a dona maria do 302 reclamou do barulho", ["maria"]),
    ("o seu josé ligou de novo", ["josé"]),
    # Apelidos comuns.
    ("Chama o Tião pra ajudar no estoque.", ["Tião"]),
    ("o zeca falou com a manu", ["zeca", "manu"]),
    # Verbo de pessoa logo depois: nome que também é palavra, e nome estrangeiro fora das listas.
    ("A Rosa ligou pedindo o boleto.", ["Rosa"]),
    ("Nguyen Van An assinou o termo.", ["Nguyen Van An"]),
])
def test_names_without_context_before(text, names):
    assert _pessoas(text) == names


@pytest.mark.parametrize("text", [
    "O Véu Pro chegou.",  # verbo que empresa e produto também "fazem": sem nome conhecido, não basta
    "A Coca Cola informou o novo preço.",
    "A rosa do jardim floresceu.",
    "Documentos de Portugal e da américa latina.",
    "o mar estava calmo e a vista da sala era bonita",
])
def test_words_that_are_not_people_stay(text):
    assert _pessoas(text) == []


@pytest.mark.parametrize("text", ["Documentos de Portugal chegaram.", "Universidade de Coimbra abriu inscrições."])
def test_word_de_place_is_not_a_person(text):
    assert _pessoas(text) == []
    assert _pessoas("O João de Portugal chegou.") == ["João de Portugal"]
