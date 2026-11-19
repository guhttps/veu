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
