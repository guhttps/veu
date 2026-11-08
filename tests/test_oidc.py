"""Login único (OIDC) no gateway: assinatura, emissor, público, validade, troca de chaves e equipes por grupo."""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature  # noqa: E402

from veu.config import Config, ConfigError, TeamConfig, load_config  # noqa: E402
from veu.server import create_app  # noqa: E402
from veu.server.oidc import OIDCError, OIDCVerifier, claim_values  # noqa: E402

ISSUER = "https://login.example.com/tenant/v2.0"
AUDIENCE = "api://veu"
NOW = 1_800_000_000
CPF = "529.982.247-25"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def as_bytes(number: int, size: int | None = None) -> bytes:
    return number.to_bytes(size or (number.bit_length() + 7) // 8, "big")


@pytest.fixture(scope="module")
def keys():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ec_key = ec.generate_private_key(ec.SECP256R1())
    numbers, point = rsa_key.public_key().public_numbers(), ec_key.public_key().public_numbers()
    jwks = {"keys": [
        {"kty": "RSA", "kid": "rsa1", "use": "sig", "n": b64(as_bytes(numbers.n)), "e": b64(as_bytes(numbers.e))},
        {"kty": "EC", "kid": "ec1", "crv": "P-256", "x": b64(as_bytes(point.x, 32)), "y": b64(as_bytes(point.y, 32))},
    ]}
    return {"rsa": rsa_key, "ec": ec_key, "jwks": jwks}


def sign(claims: dict, key, alg: str = "RS256", kid: str | None = "rsa1", header: dict | None = None) -> str:
    head = {"alg": alg, "typ": "JWT", **({"kid": kid} if kid else {}), **(header or {})}
    signing = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(claims).encode())}".encode()
    if alg == "RS256":
        signature = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
    elif alg == "PS256":
        signature = key.sign(signing, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    elif alg == "ES256":
        r, s = decode_dss_signature(key.sign(signing, ec.ECDSA(hashes.SHA256())))
        signature = as_bytes(r, 32) + as_bytes(s, 32)
    elif alg == "HS256":
        signature = hmac.new(key, signing, hashlib.sha256).digest()
    else:
        signature = b""
    return f"{signing.decode()}.{b64(signature)}"


def claims(**extra) -> dict:
    return {"iss": ISSUER, "aud": AUDIENCE, "sub": "u-1", "exp": NOW + 300, "iat": NOW, "groups": ["grp-atendimento"],
            **extra}


def verifier(keys, **kwargs) -> OIDCVerifier:
    return OIDCVerifier(ISSUER, AUDIENCE, jwks=keys["jwks"], clock=lambda: NOW, **kwargs)


def test_accepts_rs256_ps256_and_es256(keys):
    check = verifier(keys)
    assert check.verify(sign(claims(), keys["rsa"]))["sub"] == "u-1"
    assert check.verify(sign(claims(), keys["rsa"], "PS256"))["sub"] == "u-1"
    assert check.verify(sign(claims(), keys["ec"], "ES256", "ec1"))["sub"] == "u-1"
    assert check.verify(sign(claims(aud=["outro", AUDIENCE]), keys["rsa"]))["sub"] == "u-1"


@pytest.mark.parametrize("make, reason", [
    (lambda k: sign(claims(), None, "none"), "algoritmo"),
    (lambda k: sign(claims(), b"segredo-qualquer", "HS256"), "algoritmo"),       # confusão com HMAC
    (lambda k: sign(claims(), k["ec"], "ES256", "rsa1"), "assinatura"),           # chave EC no kid de RSA
    (lambda k: sign(claims(), k["rsa"], "RS256", "desconhecido"), "assinatura"),
    (lambda k: sign(claims(), rsa.generate_private_key(public_exponent=65537, key_size=2048)), "assinatura"),
    (lambda k: sign(claims(exp=NOW - 120), k["rsa"]), "expirado"),
    (lambda k: sign(claims(nbf=NOW + 600), k["rsa"]), "ainda não"),
    (lambda k: sign(claims(iss="https://outro.example"), k["rsa"]), "emissor"),
    (lambda k: sign(claims(aud="api://outro"), k["rsa"]), "público"),
    (lambda k: sign({key: value for key, value in claims().items() if key != "exp"}, k["rsa"]), "exp"),
    (lambda k: "eyJ.nao-e-jwt", "JWT"),
])
def test_rejects(keys, make, reason):
    with pytest.raises(OIDCError, match=reason):
        verifier(keys).verify(make(keys))


def test_tampered_payload_is_rejected(keys):
    token = sign(claims(), keys["rsa"])
    head, _, signature = token.split(".")
    forged = f"{head}.{b64(json.dumps(claims(groups=['admins'])).encode())}.{signature}"
    with pytest.raises(OIDCError, match="assinatura"):
        verifier(keys).verify(forged)


def test_discovery_and_key_rotation_without_hammering_the_issuer(keys):
    calls, clock = [], [NOW]
    current = {"keys": [keys["jwks"]["keys"][1]]}  # no começo, só a chave EC

    def fetch(url):
        calls.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": "https://login.example.com/keys"}
        return current

    check = OIDCVerifier(ISSUER, AUDIENCE, fetch=fetch, clock=lambda: clock[0])
    assert check.verify(sign(claims(), keys["ec"], "ES256", "ec1"))
    assert calls == [ISSUER + "/.well-known/openid-configuration", "https://login.example.com/keys"]
    current = keys["jwks"]  # o emissor passou a assinar com a RSA
    with pytest.raises(OIDCError):  # kid novo logo depois da busca: não busca de novo a cada requisição
        check.verify(sign(claims(), keys["rsa"]))
    assert len(calls) == 2
    clock[0] += 61
    assert check.verify(sign(claims(exp=clock[0] + 300), keys["rsa"]))  # passado um minuto, busca e aceita
    assert calls[-1] == "https://login.example.com/keys"


def test_background_mode_never_waits_for_a_slow_issuer(keys):
    """No servidor, a busca das chaves roda numa thread: um emissor lento não trava as requisições."""
    import threading

    release = threading.Event()

    def slow_fetch(url):
        release.wait(5)
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": "https://login.example.com/keys"}
        return keys["jwks"]

    check = OIDCVerifier(ISSUER, AUDIENCE, fetch=slow_fetch, clock=lambda: NOW, background=True)
    token = sign(claims(), keys["rsa"])
    started = time.monotonic()
    with pytest.raises(OIDCError, match="ainda não foram carregadas"):
        check.verify(token)
    assert time.monotonic() - started < 1  # recusou na hora, sem esperar o emissor
    release.set()
    for _ in range(100):
        if not check._fetching:
            break
        time.sleep(0.02)
    assert check.verify(token)["sub"] == "u-1"
    prefetched = OIDCVerifier(ISSUER, AUDIENCE, fetch=lambda url: slow_fetch(url), clock=lambda: NOW, background=True)
    prefetched.prefetch()  # no início do servidor, busca de uma vez
    assert prefetched.verify(token)["sub"] == "u-1"


def test_discovery_must_match_the_issuer(keys):
    fetch = lambda url: {"issuer": "https://falso.example", "jwks_uri": "https://falso.example/keys"}  # noqa: E731
    with pytest.raises(OIDCError, match="outro emissor"):
        OIDCVerifier(ISSUER, AUDIENCE, fetch=fetch, clock=lambda: NOW).verify(sign(claims(), keys["rsa"]))


def test_claim_values():
    assert claim_values({"groups": ["a", 1]}, "groups") == {"a", "1"}
    assert claim_values({"scp": "ler escrever"}, "scp") == {"ler", "escrever"}
    assert claim_values({}, "groups") == set()


def test_config(monkeypatch, tmp_path):
    with pytest.raises(ConfigError, match="https"):
        Config(oidc_issuer="http://login.example.com", oidc_audience="x")
    with pytest.raises(ConfigError, match="publico"):
        Config(oidc_issuer=ISSUER)
    with pytest.raises(ConfigError, match=r"\[oidc\]"):
        Config(teams={"a": TeamConfig("a", None, oidc_groups=("g",))})
    path = tmp_path / "veu.toml"
    path.write_text(f'[oidc]\nemissor = "{ISSUER}"\npublico = "{AUDIENCE}"\nclaim_equipe = "roles"\n'
                    'claim_usuario = "preferred_username"\n\n[equipes.atendimento]\ngrupos_oidc = ["Veu.Atendimento"]\n',
                    encoding="utf-8")
    config = load_config(str(path))
    assert config.oidc_team_claim == "roles" and config.teams["atendimento"].oidc_groups == ("Veu.Atendimento",)


# Gateway ---------------------------------------------------------------------------------------------------------

def gateway(keys, tmp_path, seen, **options):
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(keys["jwks"]), encoding="utf-8")

    def upstream(request):
        seen.append(request)
        text = json.loads(request.content)["messages"][-1]["content"]
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": text}}]})

    config = Config(oidc_issuer=ISSUER, oidc_audience=AUDIENCE, oidc_jwks=str(jwks), audit_log=str(tmp_path / "a.jsonl"),
                    teams={"atendimento": TeamConfig("atendimento", None, oidc_groups=("grp-atendimento",))}, **options)
    return create_app(config, upstream_transport=httpx.MockTransport(upstream))


def chat(app, text, headers):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            return await c.post("/v1/chat/completions", headers=headers,
                                json={"model": "m", "messages": [{"role": "user", "content": text}]})

    return asyncio.run(run())


def live(**extra):
    return claims(**{"exp": int(time.time()) + 300, "iat": int(time.time()), **extra})


def test_gateway_maps_groups_to_teams_and_audits_the_user(keys, tmp_path):
    seen = []
    app = gateway(keys, tmp_path, seen, oidc_user_claim="preferred_username")
    token = sign(live(preferred_username="usuario-123"), keys["rsa"])
    response = chat(app, f"CPF {CPF}", {"authorization": "Bearer sk-x", "x-veu-token": token})
    assert response.status_code == 200 and CPF in response.text
    assert "x-veu-token" not in seen[-1].headers  # o JWT da empresa nunca vai para o provedor
    record = json.loads((tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["equipe"] == "atendimento" and record["usuario"] == "usuario-123"


def test_gateway_refuses_users_outside_the_groups_and_bad_tokens(keys, tmp_path):
    app = gateway(keys, tmp_path, [])
    outsider = chat(app, "oi", {"x-veu-token": sign(live(groups=["financeiro"]), keys["rsa"])})
    assert outsider.status_code == 403 and outsider.json()["error"]["type"] == "veu_sem_equipe"
    expired = chat(app, "oi", {"x-veu-token": sign(live(exp=int(time.time()) - 600), keys["rsa"])})
    assert expired.status_code == 401 and "expirado" in expired.text
    assert chat(app, "oi", {}).status_code == 401
    relaxed = gateway(keys, tmp_path, [], oidc_require_team=False)
    assert chat(relaxed, "oi", {"x-veu-token": sign(live(groups=[]), keys["rsa"])}).status_code == 200


def marker_upstream(request):
    """IA que responde com o [CPF_1] de quem quer que esteja no cofre da sessão."""
    return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": "Resposta: [CPF_1]"}}]})


def test_oidc_users_never_share_a_session(keys, tmp_path):
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(keys["jwks"]), encoding="utf-8")
    app = create_app(Config(oidc_issuer=ISSUER, oidc_audience=AUDIENCE, oidc_jwks=str(jwks), oidc_require_team=False),
                     upstream_transport=httpx.MockTransport(marker_upstream))
    alice = {"x-veu-token": sign(live(sub="u-alice"), keys["rsa"]), "x-veu-sessao": "conversa-1"}
    bruno = {"x-veu-token": sign(live(sub="u-bruno"), keys["rsa"]), "x-veu-sessao": "conversa-1"}
    assert CPF in chat(app, f"Meu CPF é {CPF}", alice).text  # a própria Alice recebe o dado de volta
    assert CPF not in chat(app, "oi", bruno).text            # o Bruno, com o mesmo X-Veu-Sessao, não


def test_teams_with_injected_keys_never_share_a_session(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "gateway")
    app = create_app(Config(teams={"a": TeamConfig("a", "token-equipe-a"), "b": TeamConfig("b", "token-equipe-b")}),
                     upstream_transport=httpx.MockTransport(marker_upstream))
    assert CPF in chat(app, f"Meu CPF é {CPF}", {"x-veu-token": "token-equipe-a", "x-veu-sessao": "s"}).text
    assert CPF not in chat(app, "oi", {"x-veu-token": "token-equipe-b", "x-veu-sessao": "s"}).text
