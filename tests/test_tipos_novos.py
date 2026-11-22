"""Tipos novos: frase de recuperação, 2FA, Wi-Fi, tokens em links, OTP, CVV, Pix copia e cola, boleto, certidão,
RNM, IMEI, coordenadas em graus e e-mail disfarçado."""

import random

import pytest

from veu import Veu
from veu import validators as v
from veu.recognizers.secrets import bip39_indexes
from veu.surrogates import fake_boleto, fake_certidao, fake_imei

BRCODE = ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal"
          "6008BRASILIA62070503***63041D3D")  # exemplo do manual do BR Code (Banco Central)
LINHA = "34191.79001 01043.510047 91020.150008 1 96610000017500"


def labels(text: str) -> dict[str, str]:
    result = Veu().anonymize(text)
    return {r.label: r.entity.text for r in result.replacements}


def mnemonic_ok(words: str) -> bool:
    indexes = bip39_indexes()
    return v.is_valid_bip39([indexes[word] for word in words.split()])


def test_bip39_official_vectors():
    assert len(bip39_indexes()) == 2048
    assert mnemonic_ok("abandon " * 11 + "about")
    assert mnemonic_ok("legal winner thank year wave sausage worth useful legal winner thank yellow")
    assert mnemonic_ok("zoo " * 23 + "vote")
    assert not mnemonic_ok("abandon " * 12)


@pytest.mark.parametrize("text,phrase", [
    ("minha seed: abandon ability able about above absent absorb abstract absurd abuse access accident",
     "abandon ability able about above absent absorb abstract absurd abuse access accident"),
    ("Guarde: legal winner thank year wave sausage worth useful legal winner thank yellow.",
     "legal winner thank year wave sausage worth useful legal winner thank yellow"),
    ("1. legal 2. winner 3. thank 4. year 5. wave 6. sausage 7. worth 8. useful 9. legal 10. winner 11. thank 12. yellow",
     "legal 2. winner 3. thank 4. year 5. wave 6. sausage 7. worth 8. useful 9. legal 10. winner 11. thank 12. yellow"),
])
def test_wallet_recovery_phrase_is_a_private_key(text, phrase):
    assert labels(text).get("CHAVE_PRIVADA") == phrase


def test_english_words_without_context_or_checksum_stay():
    text = "about above across act action actor actual add address adult advance advice after again against age"
    assert Veu().anonymize(text).text == text


@pytest.mark.parametrize("text,label,value", [
    ("https://app.example.com/reset?token=8f3a9c2b7d1e4f6a9b0c3d5e7f1a2b4c&u=2", "SEGREDO",
     "8f3a9c2b7d1e4f6a9b0c3d5e7f1a2b4c"),
    ("otpauth://totp/Empresa:joao?issuer=X&secret=JBSWYDPEHPKXPZZZ", "SEGREDO", "JBSWYDPEHPKXPZZZ"),
    ("WIFI:T:WPA;S:CasaSouza;P:minhaSenha2024!;;", "SENHA", "minhaSenha2024!"),
    ("Seu código de verificação é 483920.", "SENHA", "483920"),
    ("cartão final 4242, validade 12/27, CVV 123", "CARTAO_CREDITO", "123"),
    (f"Pix copia e cola: {BRCODE}", "CHAVE_PIX", BRCODE),
    (f"Segue o boleto: {LINHA}", "BOLETO", LINHA),
    ("Matrícula da certidão: 104539 01 55 2013 1 00012 021 0000123 55", "CERTIDAO",
     "104539 01 55 2013 1 00012 021 0000123 55"),
    ("RNM V123456-7 do estrangeiro", "RG", "V123456-7"),
    ("IMEI do aparelho: 35-209900-176148-1", "IMEI", "35-209900-176148-1"),
    ("localização 23°33'01\"S 46°38'02\"W", "COORDENADAS", "23°33'01\"S 46°38'02\"W"),
    ("contato: joao.silva [at] gmail [dot] com", "EMAIL", "joao.silva [at] gmail [dot] com"),
    ("escreve para maria arroba empresa ponto com ponto br", "EMAIL", "maria arroba empresa ponto com ponto br"),
])
def test_new_types_are_hidden(text, label, value):
    assert labels(text).get(label) == value


@pytest.mark.parametrize("text", [
    "te vejo at home dot",  # "at" e "dot" sem domínio
    "A reunião é às 14h na sala 3; o código do produto é ABC-123.",
    "Inclinação de 45° 30' no telhado.",  # graus sem par de coordenadas
    "O número 34191790010104351004891020150008196610000017500 não é boleto.",  # 47 dígitos sem os verificadores
])
def test_lookalikes_stay(text):
    assert Veu().anonymize(text).text == text


def test_typo_in_a_formatted_boleto_line_is_still_hidden():
    assert labels("Linha: 34191.79001 01043.510048 91020.150008 1 96610000017500").get("BOLETO")


def test_imei_wins_over_card_but_card_context_wins_back():
    assert "IMEI" in labels("imei 352099001761481")
    assert "CARTAO_CREDITO" in labels("cartão de crédito 352099001761481")


def test_brcode_with_wrong_crc_is_not_a_pix_code():
    assert labels(f"Pix: {BRCODE[:-1]}E").get("CHAVE_PIX") != BRCODE[:-1] + "E"


def test_synthetic_operator_keeps_the_new_formats_valid():
    rng = random.Random(3)
    assert all(v.is_valid_imei(fake_imei(rng)) for _ in range(200))
    assert all(v.is_valid_boleto(fake_boleto(rng)) for _ in range(200))
    assert all(v.is_likely_certidao(fake_certidao(rng)) for _ in range(200))
    text = f"IMEI 35-209900-176148-1, boleto {LINHA}"
    result = Veu().with_operator("sintetico").anonymize(text)
    assert "35-209900" not in result.text and "[" not in result.text
    assert result.restore(result.text) == text


# Segunda leva: carteiras e chaves de cripto, chaves de infraestrutura, INSS, PIN e horários Unix.
@pytest.mark.parametrize("text,label,value", [
    ("manda o USDT para TJRabPrwbZy45sbavfcjinPJC18kjpRTv8 na rede TRC20", "CRIPTO", "TJRabPrwbZy45sbavfcjinPJC18kjpRTv8"),
    ("LTC: LaMT348PWRnrqeeWArpwQPbuanpXDZGEUz", "CRIPTO", "LaMT348PWRnrqeeWArpwQPbuanpXDZGEUz"),
    ("DOGE DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L", "CRIPTO", "DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L"),
    ("xpub661MyMwAqRbcFtXgS5sYJABqqG9YLmC4Q1Rdap9gSE8NqtwybGhePY2gZ29ESFjqJoCu1Rupje8YtGqsefD265TMg7usUDFdp6W1EGMcet8",
     "CRIPTO", "xpub661MyMwAqRbcFtXgS5sYJABqqG9YLmC4Q1Rdap9gSE8NqtwybGhePY2gZ29ESFjqJoCu1Rupje8YtGqsefD265TMg7usUDFdp6W1EGMcet8"),
    ("chave WIF 5HueCGU8rMjxEXxiPuD5BDku4MkFqeZyd4dZ1jvhTVqvbTLvyTJ", "CHAVE_PRIVADA",
     "5HueCGU8rMjxEXxiPuD5BDku4MkFqeZyd4dZ1jvhTVqvbTLvyTJ"),
    ("xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi",
     "CHAVE_PRIVADA",
     "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi"),
    ("minha chave privada é 4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318", "CHAVE_PRIVADA",
     "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"),
    ("AGE-SECRET-KEY-1QQPZRY9X8GF2TVDW0S3JN54KHCE6MUA7LQPZRY9X8GF2TVDW0S3JN54KHCE6MU", "CHAVE_PRIVADA",
     "AGE-SECRET-KEY-1QQPZRY9X8GF2TVDW0S3JN54KHCE6MUA7LQPZRY9X8GF2TVDW0S3JN54KHCE6MU"),
    ("client-key-data: LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVB", "CHAVE_PRIVADA",
     "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVB"),
    ("Meu benefício do INSS é NB 123.456.789-0", "CADASTRO", "123.456.789-0"),
    ("PIN do cartão: 4821, ok", "SENHA", "4821"),
    ("a senha do banco 739201", "SENHA", "739201"),
])
def test_second_batch_is_hidden(text, label, value):
    assert labels(text).get(label) == value


def test_putty_private_key_is_hidden():
    key = ("PuTTY-User-Key-File-3: ssh-ed25519\nEncryption: none\nComment: x\nPublic-Lines: 1\nAAAAC3NzaC1lZDI1NTE5\n"
           "Private-Lines: 1\nAAAAIDN3cmV0c2VjcmV0c2VjcmV0c2VjcmV0c2Vj\nPrivate-MAC: 9b2f1c")
    assert "AAAAIDN3cmV0" not in Veu().anonymize(key).text


@pytest.mark.parametrize("text", [
    "sha256: 4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318",  # hash sem "chave privada"
    "client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUM4akNDQWRxZ0F3SUJBZ0lJ",  # certificado
    "TJRabPrwbZy45sbavfcjinPJC18kjpRTv9",  # checksum errado
    "a senha expira em 2027; senha de 6 dígitos; senha alterada em 12/03/2024",
    '{"sub":"42","exp":1735689600,"iat":1735686000}',  # horário Unix num JWT não é telefone
    "GET /api?ts=1735689600&page=2 e timestamp 1735689600",
])
def test_second_batch_lookalikes_stay(text):
    assert Veu().anonymize(text).text == text


@pytest.mark.parametrize("text", ["telefone=11987654321", "fone: 1135689600", "phone=1135689600", "ligue 1135689600"])
def test_phones_with_context_still_hidden_after_a_key(text):
    assert "TELEFONE" in labels(text)


# Saldo, salário, renda e limite: o valor em dinheiro some só com o contexto antes (preço, frete e receita ficam).
@pytest.mark.parametrize(("text", "value"), [
    ("Saldo atual: R$ 15.432,10.", "R$ 15.432,10"),
    ("Ag 0001 C/C 123456-7 - saldo disponível R$ 2.350,00", "R$ 2.350,00"),
    ("meu salário este mês ficou em R$ 4500", "R$ 4500"),
    ("renda mensal de 3.200,00 reais", "3.200,00 reais"),
    ("tenho uma dívida de R$ 3 mil no cartão", "R$ 3 mil"),
    ("limite de crédito: R$ 5.000,00", "R$ 5.000,00"),
    ("balance: US$ 1,250.75", "US$ 1,250.75"),
])
def test_personal_money_amounts_are_hidden_with_context(text, value):
    assert labels(text).get("VALOR") == value


@pytest.mark.parametrize("text", [
    "O frete custa R$ 30 e o produto R$ 1.299,90",
    "faturamento de R$ 2,3 milhões no trimestre",
    "Promoção: de R$ 199,00 por R$ 149,00",
    "O plano custa R$ 9,90 por mês",
])
def test_prices_and_company_figures_stay(text):
    assert "VALOR" not in labels(text)


def test_money_synthetic_value_keeps_the_format():
    result = Veu(operator="sintetico").anonymize("Saldo atual: R$ 15.432,10")
    novo = result.text.removeprefix("Saldo atual: ")
    assert novo != "R$ 15.432,10" and novo.startswith("R$ ") and len(novo) == len("R$ 15.432,10")
