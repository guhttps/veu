"""Registro profissional, CTPS e logins nome.sobrenome: achados da simulação de uso (scripts/simular_usuarios.py)."""

import pytest

from veu import Veu


@pytest.mark.parametrize(
    "text,value",
    [
        ("por sua advogada (OAB/SP 123.456), com fundamento", "123.456"),
        ("OAB-RJ nº 98765", "98765"),
        ("Dra. Ana Lima (CRM-SC 34636)", "34636"),
        ("CRM/MG: 54.321", "54.321"),
        ("Eng. Paulo, CREA-SP 5061234567", "5061234567"),
        ("psicóloga CRP 06/123456", "06/123456"),
        ("enfermeira COREN-PR 123456", "123456"),
    ],
)
def test_professional_registration_hides_only_the_number(text, value):
    result = Veu().anonymize(text)
    found = [entity for entity in result.entities if entity.label == "REGISTRO_PROFISSIONAL"]
    assert [entity.text for entity in found] == [value]
    assert value not in result.text


@pytest.mark.parametrize(
    "text", ["Usamos o Dynamics CRM 365 e o CRM 2024", "OAB 2024: exame de ordem", "A série 3 da escola"]
)
def test_professional_registration_needs_the_state(text):
    assert Veu().anonymize(text).text == text


@pytest.mark.parametrize(
    "text", ["CTPS: 3492025 série 0533-SP", "carteira de trabalho nº 1234567, SÉRIE 00012"]
)
def test_ctps_number_and_series(text):
    labels = [entity.label for entity in Veu().anonymize(text).entities]
    assert labels == ["CTPS", "CTPS"]


@pytest.mark.parametrize(
    "text,login",
    [
        ("usuário Gislaine Vieira (login gislaine.vieira) não acessa a VPN", "gislaine.vieira"),
        ("ls /home/joao_silva/docs", "joao_silva"),
        ("ssh humberto.maciel@10.0.0.5", None),
    ],
)
def test_login_with_first_and_last_name(text, login):
    result = Veu().anonymize(text)
    if login:
        assert login not in result.text
        assert login in [entity.text for entity in result.entities]


@pytest.mark.parametrize(
    "text", ["acesse maria.souza.com.br", "abra o config.yaml e a nota.fiscal", "rosa.silva e self.costa"]
)
def test_login_rule_ignores_domains_files_and_common_words(text):
    assert Veu().anonymize(text).text == text


def test_new_labels_work_with_the_synthetic_operator():
    text = "Dra. Ana Lima (CRM-SC 34636), CTPS 3492025 série 0533-SP, login ana.lima"
    result = Veu(operator="sintetico").anonymize(text)
    assert "34636" not in result.text and "3492025" not in result.text and "ana.lima" not in result.text
    assert result.restore(result.text) == text
