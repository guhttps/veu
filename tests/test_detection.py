import random

import pytest

from veu import Analyzer, Veu
from veu import surrogates as fake


def labels(text, **options):
    return [(e.label, e.text) for e in Veu(**options).analyze(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CPF 529.982.247-25", ("CPF", "529.982.247-25")),
        ("o cpf é 52998224725", ("CPF", "52998224725")),
        ("CNPJ 11.222.333/0001-81", ("CNPJ", "11.222.333/0001-81")),
        ("CNPJ 12.ABC.345/01DE-35", ("CNPJ", "12.ABC.345/01DE-35")),
        ("ligue (11) 91234-5678", ("TELEFONE", "(11) 91234-5678")),
        ("whats +55 21 99876-5432", ("TELEFONE", "+55 21 99876-5432")),
        ("escreva para maria.souza@gmail.com", ("EMAIL", "maria.souza@gmail.com")),
        ("CEP 01310-100", ("CEP", "01310-100")),
        ("placa BRA2E19", ("PLACA", "BRA2E19")),
        ("cartão 4111 1111 1111 1111", ("CARTAO_CREDITO", "4111 1111 1111 1111")),
        ("RG: 12.345.678-9", ("RG", "12.345.678-9")),
        ("chave pix 2f1b8f4e-7c2a-4d7e-9a1b-3c5d7e9f1a2b", ("CHAVE_PIX", "2f1b8f4e-7c2a-4d7e-9a1b-3c5d7e9f1a2b")),
        ("acesso do IP 200.147.67.142", ("IP", "200.147.67.142")),
        ("data de nascimento: 12/03/1990", ("DATA_NASCIMENTO", "12/03/1990")),
        ("processo 0710802-55.2019.8.07.0001", ("PROCESSO", "0710802-55.2019.8.07.0001")),
    ],
)
def test_documents_and_contacts(text, expected):
    assert expected in labels(text)


@pytest.mark.parametrize(
    ("label", "context", "generator"),
    [
        ("CNH", "CNH", fake.fake_cnh),
        ("RENAVAM", "RENAVAM", fake.fake_renavam),
        ("PIS", "PIS", lambda rng: fake.fake_pis(rng, formatted=False)),
        ("TITULO_ELEITOR", "título de eleitor", fake.fake_titulo),
        ("CNS", "cartão SUS", fake.fake_cns),
    ],
)
def test_context_dependent_documents(label, context, generator):
    rng = random.Random(11)
    for _ in range(20):
        value = generator(rng)
        assert labels(f"{context} {value}") == [(label, value)]


def test_documents_that_look_like_other_numbers_need_context():
    assert labels("O pedido 52998224725 foi enviado") == [("CPF", "52998224725")]  # CPF válido dispensa contexto
    rng = random.Random(5)
    renavam = fake.fake_renavam(rng)
    assert ("RENAVAM", renavam) not in labels(f"Número {renavam}")


def test_dates_without_birth_context_are_not_personal():
    assert not labels("Reunião em 12/03/2026 às 10h.")


def test_invalid_formatted_cpf_is_still_hidden_by_default():
    assert labels("CPF 123.456.789-10") == [("CPF", "123.456.789-10")]
    assert not labels("valor 123.456.789-10", threshold=0.6)


def test_person_names():
    assert ("PESSOA", "Maria Aparecida da Silva") in labels("Prezada Maria Aparecida da Silva, tudo bem?")
    assert ("PESSOA", "JOSÉ CARLOS DA SILVA") in labels("NOME: JOSÉ CARLOS DA SILVA")
    assert ("PESSOA", "joão") in labels("oi joão, tudo certo?")
    assert ("PESSOA", "maria souza") in labels("falei com maria souza ontem")
    assert ("PESSOA", "Wanderley Fagundes") in labels("Quem atendeu foi o Dr. Wanderley Fagundes.")


@pytest.mark.parametrize(
    "text",
    [
        "O Banco do Brasil e o Magazine Luiza anunciaram parceria.",
        "A reunião será em São José dos Campos.",
        "Rosa é a cor do ano. Vitória do time!",
        "Avenida Paulista, Rua Augusta e Praça da Sé são pontos turísticos.",
        "A Tech Soluções Ltda abriu vagas.",
        "Março foi chuvoso em Belo Horizonte.",
    ],
)
def test_no_false_positives_for_places_and_companies(text):
    assert labels(text) == []


def test_ambiguous_names_need_context():
    assert labels("A Rosa é linda.") == []
    assert labels("Falar com a Dona Rosa amanhã.") == [("PESSOA", "Rosa")]


def test_addresses():
    found = labels("Moro na Rua das Flores, 123, apto 45, perto do centro.")
    assert ("ENDERECO", "Rua das Flores, 123, apto 45") in found
    assert ("ENDERECO", "Av. Paulista 1000, sala 12") in labels("Entregar na Av. Paulista 1000, sala 12.")
    assert labels("O protesto foi na Avenida Paulista.") == []


def test_address_contains_person_name():
    assert labels("Fica na Rua João Pessoa, 50.") == [("ENDERECO", "Rua João Pessoa, 50")]


def test_allowlist_and_label_filter():
    text = "Contato: suporte@empresa.com.br, CNPJ 11.222.333/0001-81, CPF 529.982.247-25"
    found = labels(text, allowlist=("suporte@empresa.com.br", "11222333000181"))
    assert found == [("CPF", "529.982.247-25")]
    assert labels(text, labels=("EMAIL",)) == [("EMAIL", "suporte@empresa.com.br")]


def test_custom_patterns():
    veu = Veu(custom_patterns=({"entidade": "MATRICULA", "padrao": r"MAT-\d{6}", "pontuacao": 0.9},))
    assert [(e.label, e.text) for e in veu.analyze("Aluno MAT-123456")] == [("MATRICULA", "MAT-123456")]


def test_analyzer_is_empty_safe():
    assert Analyzer().analyze("") == []
