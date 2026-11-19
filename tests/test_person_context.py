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
