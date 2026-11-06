"""Segredos: chaves de API, tokens, senhas, chaves privadas e URLs de conexão.

Os valores são montados na hora, em pedaços, para nenhum scanner de segredos confundir o teste com uma chave real.
"""

import random

import pytest

from veu import Veu
from veu.anonymizer import mask_value
from veu.recognizers.secrets import key_kind, looks_random

RNG = random.Random(7)
ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
HEX = "0123456789abcdef"


def chars(count: int, alphabet: str = ALNUM) -> str:
    return "".join(RNG.choice(alphabet) for _ in range(count))


def key(*parts: str) -> str:
    return "".join(parts)


veu = Veu()


def labels(text: str) -> list[tuple[str, str]]:
    return [(entity.label, entity.text) for entity in veu.analyze(text)]


PROVIDER_KEYS = [
    key("sk-", "proj-", chars(20), "T3Blbk", chars(20)),
    key("sk-", "ant-", "api03-", chars(93), "AA"),
    key("AI", "za", chars(35)),
    key("AK", "IA", chars(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")),
    key("gh", "p_", chars(36)),
    key("github", "_pat_", chars(22), "_", chars(59)),
    key("gl", "pat-", chars(20)),
    key("xo", "xb-", chars(12, "0123456789"), "-", chars(24)),
    key("sk", "_live_", chars(24)),
    key("S", "G.", chars(22), ".", chars(43)),
    key("h", "f_", chars(34)),
    key("gs", "k_", chars(52)),
    key("np", "m_", chars(36)),
    key("nt", "n_", chars(46)),
    key("APP", "_USR-", chars(16, "0123456789"), "-", chars(6, "0123456789"), "-", chars(32, HEX), "-",
        chars(9, "0123456789")),
    key("$aa", "ct_", chars(60)),
    key(chars(10, "0123456789"), ":A", "A", chars(33)),
]


@pytest.mark.parametrize("secret", PROVIDER_KEYS)
def test_provider_keys_are_detected_whole(secret):
    assert labels(f"use a chave {secret} no servidor") == [("CHAVE_API", secret)]


def test_assignments_find_generic_secrets_and_passwords():
    value = chars(32)
    text = f'API_KEY={value}\nconst c = {{ clientSecret: "{chars(4)}9{chars(20)}" }}\nDB_PASSWORD=hunter2!'
    found = labels(text)
    assert ("SEGREDO", value) in found
    assert ("SENHA", "hunter2!") in found
    assert [label for label, _ in found].count("SEGREDO") == 2


def test_header_api_key_and_bearer_token():
    jwt = key("eyJ", chars(20), ".eyJ", chars(40), ".", chars(43))
    opaque = chars(40)
    assert labels(f"X-Api-Key: {opaque}") == [("SEGREDO", opaque)]
    assert labels(f"Authorization: Bearer {jwt}") == [("TOKEN", jwt)]
    assert labels(f"Authorization: Bearer {opaque}") == [("TOKEN", opaque)]


def test_password_in_prose():
    assert labels("a senha do wifi é Gato2024") == [("SENHA", "Gato2024")]
    assert labels("minha senha: Abc@1234") == [("SENHA", "Abc@1234")]


@pytest.mark.parametrize("text", [
    "Senha: deve conter 8 caracteres",
    "a senha é forte",
    "password = getpass()",
    "password: ${DB_PASS}",
    "senha = os.environ.get",
    "OPENAI_API_KEY=YOUR_API_KEY",
    "api_key: sua_chave_aqui",
    "max_tokens: 2048, tokenizer: bert-base-uncased-v2",
    "token_url: https://auth.example.com/oauth/token",
    "password: string",
    "Use o modelo sk-learn para classificar",
    "secret_name: my-app-secret",
    "password: [SENHA_1]",
])
def test_not_secrets(text):
    assert labels(text) == []


def test_private_key_block_and_escaped_json_form():
    body = chars(64)
    pem = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n{body}\n-----END RSA PRIVATE KEY-----"
    assert labels(f"chave:\n{pem}\nfim") == [("CHAVE_PRIVADA", pem)]
    escaped = f'"-----BEGIN PRIVATE KEY-----\\n{body}\\n-----END PRIVATE KEY-----\\n"'
    found = labels(escaped)
    assert found and found[0][0] == "CHAVE_PRIVADA" and body in found[0][1]


def test_connection_url_keeps_trailing_punctuation_out():
    url = "postgres://admin:S3nh4Forte@db.interna.example:5432/app"
    assert labels(f"conecte em {url}.") == [("URL_CONEXAO", url)]


def test_iban_and_international_phone():
    assert labels("IBAN DE89 3704 0044 0532 0130 00") == [("IBAN", "DE89 3704 0044 0532 0130 00")]
    assert labels("IBAN DE88 3704 0044 0532 0130 00") == []  # dígitos verificadores errados
    assert labels("ligue +1 415 555 2671") == [("TELEFONE", "+1 415 555 2671")]
    assert labels("tel +44 20 7946 0958") == [("TELEFONE", "+44 20 7946 0958")]


def test_round_trip_restores_secrets_locally():
    secret = PROVIDER_KEYS[0]
    session = veu.session()
    masked = session.anonymize(f"OPENAI_API_KEY={secret}")
    assert secret not in masked and "[CHAVE_API_1]" in masked
    assert session.restore("Defina [CHAVE_API_1] no .env") == f"Defina {secret} no .env"


def test_synthetic_secret_keeps_prefix_but_changes_value():
    secret = PROVIDER_KEYS[4]
    result = veu.with_operator("sintetico").anonymize(f"token {secret}")
    replaced = result.text.removeprefix("token ")
    assert replaced.startswith(key("gh", "p_")) and replaced != secret and len(replaced) == len(secret)
    pem = f"-----BEGIN PRIVATE KEY-----\\n{chars(48)}\\n-----END PRIVATE KEY-----"
    result = veu.with_operator("sintetico").anonymize(pem)
    assert pem[30:60] not in result.text and result.text.startswith("-----BEGIN PRIVATE KEY-----\\n")


def test_masks_never_reveal_the_secret():
    assert mask_value("CHAVE_API", PROVIDER_KEYS[0]) == "sk-proj-****"
    assert mask_value("SENHA", "hunter2!") == "********"
    assert mask_value("URL_CONEXAO", "postgres://a:b@c") == "postgres://****"


def test_detector_can_be_turned_off():
    secret = PROVIDER_KEYS[4]
    without = Veu(detectors=("padroes", "nomes", "enderecos"))
    assert without.analyze(f"token {secret}") == []


@pytest.mark.parametrize(("name", "kind"), [
    ("DB_PASSWORD", "SENHA"), ("senha", "SENHA"), ("clientSecret", "SEGREDO"), ("X-Api-Key", "SEGREDO"),
    ("aws_secret_access_key", "SEGREDO"), ("accessToken", "SEGREDO"), ("chave_api", "SEGREDO"),
    ("max_tokens", None), ("token_url", None), ("secret_name", None), ("nome", None),
])
def test_key_kind(name, kind):
    assert key_kind(name) == kind


def test_looks_random():
    assert looks_random(chars(30))
    assert not looks_random("my-app-secret")
    assert not looks_random("process.env.API")
