import asyncio
import json

import httpx
import pytest

from veu.config import Config, ProviderConfig
from veu.server import create_app, resolve_route

PII = "Sou o Carlos Souza, CPF 529.982.247-25."


class Upstream:
    """Provedor de IA falso: guarda as requisições e responde com marcadores."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "modelo"}]})
        body = json.loads(request.content)
        if body.get("stream"):
            chunks = ["Olá [PES", "SOA_1], CPF [CPF_1]."]
            sse = "".join(
                "data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]}) + "\n\n"
                for c in chunks
            ) + "data: [DONE]\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"content": [{"type": "text", "text": "Olá [PESSOA_1]"}]})
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": "Olá [PESSOA_1], CPF [CPF_1]."}}]})

    @property
    def last_body(self) -> dict:
        return json.loads(self.requests[-1].content)


def call(app, method, path, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8787") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


@pytest.fixture
def upstream():
    return Upstream()


def make_app(upstream, **options):
    return create_app(Config(**options), upstream_transport=httpx.MockTransport(upstream))


def chat(content, **extra):
    return {"model": "m", "messages": [{"role": "user", "content": content}], **extra}


def test_routes_by_provider_prefix_and_format():
    config = Config()
    assert resolve_route("/v1/chat/completions", config)[1] == "https://api.openai.com/v1/chat/completions"
    assert resolve_route("/groq/v1/chat/completions", config)[1] == "https://api.groq.com/openai/v1/chat/completions"
    assert resolve_route("/ollama/v1/embeddings", config)[1] == "http://localhost:11434/v1/embeddings"
    assert resolve_route("/v1/messages", config)[1] == "https://api.anthropic.com/v1/messages"
    assert resolve_route("/v1beta/models/g:generateContent", config)[1] == (
        "https://generativelanguage.googleapis.com/v1beta/models/g:generateContent"
    )
    custom = Config(providers={**config.providers, "interno": ProviderConfig("interno", "openai", "http://ia.local/v1")},
                    default_provider="interno")
    assert resolve_route("/v1/chat/completions", custom)[1] == "http://ia.local/v1/chat/completions"


def test_proxy_hides_and_restores(upstream):
    response = call(make_app(upstream), "POST", "/v1/chat/completions", json=chat(PII),
                    headers={"Authorization": "Bearer sk-cliente"})
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Olá Carlos Souza, CPF 529.982.247-25."
    assert response.headers["x-veu-entidades"] == "CPF=1, PESSOA=1"
    sent = upstream.requests[-1]
    assert "529.982.247-25" not in sent.content.decode() and "Carlos" not in sent.content.decode()
    assert sent.headers["authorization"] == "Bearer sk-cliente"
    assert sent.headers["accept-encoding"] == "identity"


def test_proxy_streaming(upstream):
    response = call(make_app(upstream), "POST", "/groq/v1/chat/completions", json=chat(PII, stream=True))
    contents = [json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                for line in response.text.splitlines() if line.startswith("data: {")]
    assert "".join(contents) == "Olá Carlos Souza, CPF 529.982.247-25."
    assert str(upstream.requests[-1].url) == "https://api.groq.com/openai/v1/chat/completions"


def test_anthropic_route(upstream):
    payload = {"model": "c", "max_tokens": 10, "messages": [{"role": "user", "content": PII}]}
    response = call(make_app(upstream), "POST", "/v1/messages", json=payload, headers={"x-api-key": "k"})
    assert response.json()["content"][0]["text"] == "Olá Carlos Souza"
    assert upstream.requests[-1].headers["x-api-key"] == "k"
    assert "marcadores" in upstream.last_body["system"]


def test_get_requests_pass_through(upstream):
    response = call(make_app(upstream), "GET", "/v1/models")
    assert response.json() == {"data": [{"id": "modelo"}]}


def test_unknown_post_endpoints_are_blocked_by_default(upstream):
    response = call(make_app(upstream), "POST", "/v1/audio/transcriptions", content=b"audio")
    assert response.status_code == 501
    assert not upstream.requests
    allowed = call(make_app(upstream, unknown_endpoints="repassar"), "POST", "/v1/files", json={"a": 1})
    assert allowed.status_code == 200


def test_block_policy_returns_provider_style_error(upstream):
    app = make_app(upstream, block=("CARTAO_CREDITO",))
    response = call(app, "POST", "/v1/chat/completions", json=chat("cartão 4111 1111 1111 1111"))
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "veu_bloqueado"
    assert response.headers["x-veu-bloqueado"] == "CARTAO_CREDITO"
    assert not upstream.requests


def test_session_keeps_tokens_between_requests(upstream):
    app = make_app(upstream)
    headers = {"X-Veu-Sessao": "conversa-1"}
    call(app, "POST", "/v1/chat/completions", json=chat("CPF 111.444.777-35"), headers=headers)
    call(app, "POST", "/v1/chat/completions", json=chat(PII), headers=headers)
    assert upstream.last_body["messages"][-1]["content"] == "Sou o [PESSOA_1], CPF [CPF_2]."
    assert "x-veu-sessao" not in upstream.requests[-1].headers


def test_rest_api_and_playground(upstream):
    app = make_app(upstream)
    anonymized = call(app, "POST", "/veu/v1/anonimizar", json={"texto": PII}).json()
    assert anonymized["texto"] == "Sou o [PESSOA_1], CPF [CPF_1]."
    restored = call(app, "POST", "/veu/v1/restaurar", json={"texto": "[PESSOA_1]", "sessao": anonymized["sessao"]})
    assert restored.json() == {"texto": "Carlos Souza"}
    assert call(app, "POST", "/veu/v1/restaurar", json={"texto": "x", "sessao": "nao-existe"}).status_code == 404
    detected = call(app, "POST", "/veu/v1/detectar", json={"texto": PII}).json()["entidades"]
    assert [item["entidade"] for item in detected] == ["PESSOA", "CPF"]
    masked = call(app, "POST", "/veu/v1/anonimizar", json={"texto": PII, "operador": "mascara"}).json()
    assert "***.982.247-**" in masked["texto"]
    assert "Véu" in call(app, "GET", "/veu/playground").text
    assert call(app, "POST", "/veu/v1/anonimizar", json={"sem": "texto"}).status_code == 400


def test_token_protects_everything_but_health(upstream):
    app = make_app(upstream, token="segredo")
    assert call(app, "GET", "/veu/saude").status_code == 200
    assert call(app, "POST", "/v1/chat/completions", json=chat(PII)).status_code == 401
    assert call(app, "POST", "/veu/v1/detectar", json={"texto": PII}).status_code == 401
    ok = call(app, "POST", "/v1/chat/completions", json=chat(PII), headers={"X-Veu-Token": "segredo"})
    assert ok.status_code == 200
    assert "x-veu-token" not in upstream.requests[-1].headers


def test_server_side_keys_are_opt_in(upstream, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-servidor")
    call(make_app(upstream), "POST", "/v1/chat/completions", json=chat("oi"))
    assert "authorization" not in upstream.requests[-1].headers
    call(make_app(upstream, inject_keys=True), "POST", "/v1/chat/completions", json=chat("oi"))
    assert upstream.requests[-1].headers["authorization"] == "Bearer sk-servidor"


def test_audit_log_has_counts_but_no_values(upstream, tmp_path):
    log = tmp_path / "auditoria.jsonl"
    app = make_app(upstream, audit_log=str(log))
    call(app, "POST", "/v1/chat/completions", json=chat(PII))
    record = json.loads(log.read_text(encoding="utf-8").strip())
    assert record["entidades"] == {"CPF": 1, "PESSOA": 1}
    assert "529" not in log.read_text(encoding="utf-8") and "Carlos" not in log.read_text(encoding="utf-8")
    stats = call(app, "GET", "/veu/estatisticas").json()
    assert stats["dados_escondidos"] == 2 and stats["por_provedor"] == {"openai": 1}


def test_upstream_failure_returns_502():
    def broken(request):
        raise httpx.ConnectError("recusado", request=request)

    app = create_app(Config(), upstream_transport=httpx.MockTransport(broken))
    response = call(app, "POST", "/v1/chat/completions", json=chat(PII))
    assert response.status_code == 502
    assert "openai" in response.json()["error"]["message"]
