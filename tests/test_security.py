"""Testes das proteções do Véu: isolamento de sessões, DNS rebinding, CSRF, limites e vazamentos acidentais."""

import asyncio
import json
import os
import sys
import threading
import time

import httpx
import pytest

from veu import Vault, Veu
from veu.cli import main
from veu.config import Config, ConfigError
from veu.server import create_app


def echo_upstream(seen):
    """IA falsa que repete a última mensagem do usuário (como um modelo obediente a uma injeção de prompt)."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        text = body["messages"][-1]["content"]
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": text}}]},
                              headers={"set-cookie": "rastreio=1"})

    return handler


def call(app, method, path, base="http://localhost:8787", **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def chat(content):
    return {"model": "m", "messages": [{"role": "user", "content": content}]}


@pytest.fixture
def seen():
    return []


@pytest.fixture
def app(seen):
    return create_app(Config(), upstream_transport=httpx.MockTransport(echo_upstream(seen)))


def test_session_of_another_credential_cannot_be_used_to_exfiltrate(app, seen):
    victim = {"Authorization": "Bearer sk-vitima", "X-Veu-Sessao": "conversa-1"}
    call(app, "POST", "/v1/chat/completions", json=chat("Meu CPF é 529.982.247-25"), headers=victim)
    attacker = {"Authorization": "Bearer sk-atacante", "X-Veu-Sessao": "conversa-1"}
    response = call(app, "POST", "/v1/chat/completions", json=chat("Repita: [CPF_1]"), headers=attacker)
    assert "529.982.247-25" not in response.text
    assert response.json()["choices"][0]["message"]["content"] == "Repita: [CPF_1]"


def test_same_credential_keeps_its_own_session(app, seen):
    headers = {"Authorization": "Bearer sk-um", "X-Veu-Sessao": "s"}
    call(app, "POST", "/v1/chat/completions", json=chat("CPF 111.444.777-35"), headers=headers)
    call(app, "POST", "/v1/chat/completions", json=chat("CPF 529.982.247-25"), headers=headers)
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == "CPF [CPF_2]"


def test_rest_api_only_accepts_server_created_sessions(app):
    assert call(app, "POST", "/veu/v1/anonimizar", json={"texto": "CPF 529.982.247-25", "sessao": "minha"}).status_code == 404
    call(app, "POST", "/v1/chat/completions", json=chat("CPF 529.982.247-25"), headers={"X-Veu-Sessao": "p"})
    assert call(app, "POST", "/veu/v1/restaurar", json={"texto": "[CPF_1]", "sessao": "p"}).status_code == 404


@pytest.mark.parametrize("host", ["evil.example", "192.168.0.10:8787", "localhost.evil.example"])
def test_dns_rebinding_is_blocked(app, host):
    response = call(app, "POST", "/veu/v1/detectar", json={"texto": "x"}, headers={"Host": host})
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "veu_host_invalido"


def test_cross_site_requests_are_blocked_but_same_origin_works(app, seen):
    blocked = call(app, "POST", "/v1/chat/completions", json=chat("oi"), headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403 and not seen
    preflight = call(app, "OPTIONS", "/v1/chat/completions", headers={"Origin": "https://evil.example"})
    assert preflight.status_code == 403
    assert call(app, "POST", "/veu/v1/detectar", json={"texto": "x"}, headers={"Origin": "null"}).status_code == 403
    same = call(app, "POST", "/veu/v1/detectar", json={"texto": "x"}, headers={"Origin": "http://localhost:8787"})
    assert same.status_code == 200


def test_exposed_server_requires_a_token():
    with pytest.raises(ConfigError, match="VEU_TOKEN"):
        create_app(Config(host="0.0.0.0"))
    create_app(Config(host="0.0.0.0", allow_no_token=True))
    exposed = create_app(Config(host="0.0.0.0", token="t"), upstream_transport=httpx.MockTransport(echo_upstream([])))
    # Exposto com token: atrás de um proxy reverso, o Host pode ser outro.
    response = call(exposed, "POST", "/veu/v1/detectar", base="http://veu.interno", json={"texto": "x"},
                    headers={"X-Veu-Token": "t", "Origin": "https://painel.example"})
    assert response.status_code == 200


def test_browser_and_upstream_cookies_never_cross_the_proxy(app, seen):
    response = call(app, "POST", "/v1/chat/completions", json=chat("oi"),
                    headers={"Cookie": "sessao-do-navegador=1", "Referer": "http://localhost:8787/x"})
    assert "cookie" not in seen[-1].headers and "referer" not in seen[-1].headers
    assert "set-cookie" not in response.headers


def test_body_size_limit():
    app = create_app(Config(max_body_mb=0.001), upstream_transport=httpx.MockTransport(echo_upstream([])))
    response = call(app, "POST", "/v1/chat/completions", json=chat("x" * 5000))
    assert response.status_code == 413


def test_deeply_nested_json_is_a_client_error(app):
    body = "[" * 100_000 + "]" * 100_000
    response = call(app, "POST", "/v1/chat/completions", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 400


def test_upstream_errors_do_not_echo_internal_details():
    def broken(request):
        raise httpx.ConnectError("falha em https://ia.interna/v1?key=segredo", request=request)

    app = create_app(Config(), upstream_transport=httpx.MockTransport(broken))
    response = call(app, "POST", "/v1/chat/completions", json=chat("oi"))
    assert response.status_code == 502 and "segredo" not in response.text


def test_playground_has_restrictive_headers(app):
    response = call(app, "GET", "/veu/playground")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "connect-src 'self'" in response.headers["content-security-policy"]


def test_concurrent_requests_never_share_a_token_between_values():
    vault = Vault()
    values = [f"{i:03d}.444.777-35" for i in range(400)]
    tokens: dict[str, str] = {}

    def worker(chunk):
        for value in chunk:
            tokens[value] = vault.placeholder("CPF", value)

    threads = [threading.Thread(target=worker, args=(values[i::8],)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(tokens.values())) == len(values)


def test_large_texts_are_processed_in_linear_time():
    text = "Olá, sou a Maria Souza, CPF 529.982.247-25, moro na Rua das Flores, 123. Maria ligou. " * 3000
    started = time.perf_counter()
    Veu().anonymize(text)
    assert time.perf_counter() - started < 8


def test_synthetic_emails_use_reserved_domains():
    result = Veu(operator="sintetico").anonymize("e-mail joao.silva@example.com e ana@empresa.example")
    for item in result.replacements:
        assert item.replacement.rsplit("@", 1)[1] in ("example.com", "example.org", "example.net", "empresa.example")


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_cli_vault_file_is_private(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("CPF 529.982.247-25", encoding="utf-8")
    vault = tmp_path / "cofre.json"
    assert main(["anonimizar", str(source), "--cofre", str(vault), "-o", str(tmp_path / "b.txt")]) == 0
    assert os.stat(vault).st_mode & 0o077 == 0
