"""Achados da terceira rodada da simulação de uso (técnicos lidando com acessos e mais tipos de dados)."""

import pytest

from veu import Veu


def labels(text):
    return [(entity.label, entity.text) for entity in Veu().anonymize(text).entities]


@pytest.mark.parametrize(
    "text,password",
    [
        ("Login admin, senha bGsEDD$34. Fim", "bGsEDD$34"),
        ("rede Empresa_Visitantes, senha F73rbT@27.", "F73rbT@27"),
        ("usuário admin senha admin123", "admin123"),
    ],
)
def test_password_right_after_the_word(text, password):
    assert ("SENHA", password) in labels(text)


@pytest.mark.parametrize(
    "text", ["senha inválida", "senha 123456", "senha alterada com sucesso", "a senha forte é importante"]
)
def test_bare_password_needs_a_password_shape(text):
    assert Veu().anonymize(text).text == text


def test_session_cookies_are_secrets():
    text = "Cookie: session_id=d8a3d4d8bd11e4f65709e86bed6dfd05; theme=dark\nSet-Cookie: PHPSESSID=9a8b7c6d5e4f3a2b1c0d; path=/"
    found = labels(text)
    assert ("SEGREDO", "d8a3d4d8bd11e4f65709e86bed6dfd05") in found
    assert ("SEGREDO", "9a8b7c6d5e4f3a2b1c0d") in found
    assert "theme=dark" in Veu().anonymize(text).text


def test_birthdates_in_table_rows_follow_the_column_header():
    text = ("INSERT INTO clientes (id, nome, nascimento) VALUES\n(1021, 'Ana Lima', '1985-04-03'),\n"
            "(1022, 'Rui Costa', '1990-12-01');")
    found = labels(text)
    assert ("DATA_NASCIMENTO", "1985-04-03") in found and ("DATA_NASCIMENTO", "1990-12-01") in found
    assert ("DATA_NASCIMENTO", "03/04/1985") in labels("nome;nascimento\nAna Lima;03/04/1985")


def test_other_dates_in_a_table_stay():
    text = "SELECT * FROM pedidos WHERE criado_em > '2026-01-01' AND id = 7"
    assert Veu().anonymize(text).text == text


def test_mac_addresses():
    found = labels("MAC 95:7F:76:CE:A3:DA e 1c-bb-bd-4a-58-ad; ether aabb.ccdd.eeff")
    assert [label for label, _ in found] == ["MAC", "MAC", "MAC"]
    text = "broadcast FF:FF:FF:FF:FF:FF, reunião 10:30, cisco aabb.ccdd.eeff"
    assert Veu().anonymize(text).text == text


def test_gps_coordinates():
    assert ("COORDENADAS", "-19.376349, -47.473154") in labels("Local do sinistro (app): -19.376349, -47.473154.")
    assert ("COORDENADAS", "12.3456, 45.6789") in labels("coordenadas 12.3456, 45.6789")
    assert Veu().anonymize("média 12.3456, 45.6789 ponto").text == "média 12.3456, 45.6789 ponto"


def test_registration_numbers_with_context():
    text = "Prontuário: 2412179 e RA 2024631292, carteirinha 91483354148818137, apólice nº 334553733535"
    assert [label for label, _ in labels(text)] == ["CADASTRO"] * 4


def test_registration_context_keeps_dates_and_money():
    text = "matrícula feita em 12/03/2024 e apólice com prêmio de R$ 1.234,56"
    assert Veu().anonymize(text).text == text


def test_url_encoded_email():
    text = "https://loja.example/checkout?email=olga.costa%40example.org&cupom=BLACK10"
    assert ("EMAIL", "olga.costa%40example.org") in labels(text)
    assert "cupom=BLACK10" in Veu().anonymize(text).text


def test_street_without_number_in_invoice_xml():
    text = "<enderDest><xLgr>Avenida Moisés Martins</xLgr><nro>120</nro></enderDest>"
    assert ("ENDERECO", "Avenida Moisés Martins") in labels(text)
    assert Veu().anonymize("Batida traseira na Av. Paulista.").text == "Batida traseira na Av. Paulista."
