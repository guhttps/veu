"""Textos em outros idiomas: nomes fora das listas, endereços, códigos postais, telefones e nascimento."""

import pytest

from veu import Veu


def labels(text: str) -> dict[str, str]:
    return {r.label: r.entity.text for r in Veu().anonymize(text).replacements}


@pytest.mark.parametrize("text,label,value", [
    ("My name is Priya Sharma.", "PESSOA", "Priya Sharma"),
    ("Me llamo Oluwaseun Adeyemi y necesito ayuda.", "PESSOA", "Oluwaseun Adeyemi"),
    ("Je m'appelle Thibault Lefebvre.", "PESSOA", "Thibault Lefebvre"),
    ("Ich heiße Jürgen Schwarzkopf.", "PESSOA", "Jürgen Schwarzkopf"),
    ("Mi chiamo Gianluca Bianchi.", "PESSOA", "Gianluca Bianchi"),
    ("Herr Schwarzkopf ruft an.", "PESSOA", "Schwarzkopf"),
    ("La Señora Okonkwo llamó.", "PESSOA", "Okonkwo"),
    ("Falei com a Senhora Okonkwo.", "PESSOA", "Okonkwo"),
    ("Call me at (415) 555-0132.", "TELEFONE", "(415) 555-0132"),
    ("Me llamo Juan, tel 55 1234 5678.", "TELEFONE", "55 1234 5678"),
    ("telemóvel 912 345 678", "TELEFONE", "912 345 678"),
    ("Handy 0151 23456789", "TELEFONE", "0151 23456789"),
    ("Your address: 742 Evergreen Terrace, Springfield, IL 62704.", "ENDERECO", "742 Evergreen Terrace"),
    ("Your address: 742 Evergreen Terrace, Springfield, IL 62704.", "CEP", "62704"),
    ("vivo en Calle Mayor 15, 28013 Madrid.", "ENDERECO", "Calle Mayor 15"),
    ("vivo en Calle Mayor 15, 28013 Madrid.", "CEP", "28013"),
    ("j'habite 10 rue de Rivoli, 75001 Paris.", "ENDERECO", "10 rue de Rivoli"),
    ("wohnhaft in der Hauptstraße 5, 10115 Berlin.", "ENDERECO", "Hauptstraße 5"),
    ("morada Rua Augusta 100, 1100-053 Lisboa.", "CEP", "1100-053"),
    ("né le 12/03/1985", "DATA_NASCIMENTO", "12/03/1985"),
    ("geboren am 01.02.1980", "DATA_NASCIMENTO", "01.02.1980"),
    ("nacido el 03/04/1979", "DATA_NASCIMENTO", "03/04/1979"),
])
def test_foreign_text_is_hidden(text, label, value):
    assert labels(text).get(label) == value


@pytest.mark.parametrize("text", [
    "Em 2023, 12345 Pessoas visitaram.",
    "Im Jahr 2023, 12345 Besucher kamen.",  # em alemão todo substantivo tem maiúscula
    "tel 2023 e 2024 foram anos bons",
    "O professor explicou a matéria.",
])
def test_foreign_lookalikes(text):
    assert Veu().anonymize(text).text == text
