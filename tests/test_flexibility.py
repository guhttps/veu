"""Testes das opções de flexibilidade: plugins, exceções, sessões, regras por provedor, Ollama, arquivos e relatórios."""

import asyncio
import json
import random
import textwrap

import httpx
import pytest

import veu
from veu import Veu
from veu.cli import main
from veu.config import Config, ConfigError, load_config
from veu.gateway import Gateway, detect_adapter
from veu.gateway.sse import NDJSONTransformer
from veu.recognizers import Candidate
from veu.reporting import check_text, render, sarif
from veu.server import create_app, resolve_route

PII = "Sou a Maria Souza, CPF 529.982.247-25."


class MatriculaRecognizer:
    name = "matricula"
    labels = frozenset({"MATRICULA"})

    def find(self, text):
        index = text.find("MAT-")
        if index != -1:
            yield Candidate("MATRICULA", index, index + 10, 0.9, self.name)


def test_allow_patterns_keep_company_data_visible():
    instance = Veu(allow_patterns=(r"@minhaempresa\.example$",))
    text = "Fale com suporte@minhaempresa.example ou com joana@example.com"
    assert instance.anonymize(text).text == "Fale com suporte@minhaempresa.example ou com [EMAIL_1]"
    with pytest.raises(ConfigError, match="ignorar_padroes"):
        Config(allow_patterns=("(",))


def test_extra_recognizers_and_plugins_by_import_path(tmp_path, monkeypatch):
    assert Veu(extra_recognizers=[MatriculaRecognizer()]).anonymize("Aluno MAT-123456").text == "Aluno [MATRICULA_1]"
    module = tmp_path / "meus_detectores.py"
    module.write_text(textwrap.dedent('''
        from veu.recognizers import Candidate

        class Placa:
            name = "placa-interna"
            labels = frozenset({"PATRIMONIO"})

            def find(self, text):
                index = text.find("PAT")
                if index != -1:
                    yield Candidate("PATRIMONIO", index, index + 8, 0.9, self.name)
    '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    instance = Veu(detectors=("padroes", "meus_detectores:Placa"))
    assert instance.anonymize("Item PAT00123 do CPF 529.982.247-25").text == "Item [PATRIMONIO_1] do CPF [CPF_1]"
    with pytest.raises(ConfigError, match="Detectores desconhecidos"):
        Config(detectors=("inexistente",))


def test_session_shares_one_vault_and_handles_structures():
    with veu.session() as session:
        messages = session.anonymize_data([{"role": "user", "content": PII}, ("tupla", "CPF 529.982.247-25")])
        assert messages[0]["content"] == "Sou a [PESSOA_1], CPF [CPF_1]."
        assert messages[1] == ("tupla", "CPF [CPF_1]")
        assert session.anonymize("Maria Souza ligou") == "[PESSOA_1] ligou"
        assert session.restore_data({"resposta": "Olá [PESSOA_1]"}) == {"resposta": "Olá Maria Souza"}
        assert "".join(session.restore_stream(["Oi [PES", "SOA_1]"])) == "Oi Maria Souza"
        assert session.counts == {"PESSOA": 2, "CPF": 2}


def test_with_operator_reuses_detectors():
    base = Veu()
    masked = base.with_operator("mascara")
    assert masked.analyzer is base.analyzer
    assert masked.anonymize("CPF 529.982.247-25").text == "CPF ***.982.247-**"


# Ollama nativo ---------------------------------------------------------------------------------------------------

def test_ollama_native_routes_and_masking():
    config = Config()
    assert resolve_route("/api/chat", config)[1] == "http://localhost:11434/api/chat"
    assert resolve_route("/ollama/api/generate", config)[1] == "http://localhost:11434/api/generate"
    assert resolve_route("/ollama/v1/chat/completions", config)[1] == "http://localhost:11434/v1/chat/completions"
    gateway = Gateway(Veu())
    adapter = detect_adapter("POST", "/api/generate")
    prepared = gateway.prepare(adapter, json.dumps({"model": "m", "prompt": PII}).encode(), path="/api/generate")
    body = json.loads(prepared.body)
    assert body["prompt"] == "Sou a [PESSOA_1], CPF [CPF_1]." and "marcadores" in body["system"]
    assert prepared.stream  # o Ollama faz streaming por padrão


@pytest.mark.parametrize("seed", range(4))
def test_ollama_ndjson_stream_restore(seed):
    gateway = Gateway(Veu())
    adapter = detect_adapter("POST", "/api/chat")
    prepared = gateway.prepare(adapter, json.dumps({"model": "m", "messages": [{"role": "user", "content": PII}]}).encode(),
                               path="/api/chat")
    lines = [{"message": {"role": "assistant", "content": c}, "done": False} for c in ["Olá [PES", "SOA_1], CPF [CP", "F_1]"]]
    lines.append({"message": {"role": "assistant", "content": ""}, "done": True})
    raw = "".join(json.dumps(line) + "\n" for line in lines).encode()
    transformer = gateway.stream(prepared, "application/x-ndjson")
    assert isinstance(transformer, NDJSONTransformer)
    rng, output, position = random.Random(seed), b"", 0
    while position < len(raw):
        size = rng.randint(1, 7)
        output += transformer.feed(raw[position:position + size])
        position += size
    output += transformer.close()
    events = [json.loads(line) for line in output.decode().splitlines() if line]
    assert "".join(event["message"]["content"] for event in events) == "Olá Maria Souza, CPF 529.982.247-25"
    assert events[-1]["done"] is True


# Proxy: regras por provedor, operador por requisição e métricas ----------------------------------------------------

def call(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def echo(seen):
    def handler(request):
        seen.append(request)
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/api/chat"):
            lines = [{"message": {"content": "Olá [PESSOA_1]"}, "done": False}, {"message": {"content": ""}, "done": True}]
            return httpx.Response(200, headers={"content-type": "application/x-ndjson"},
                                  content="".join(json.dumps(x) + "\n" for x in lines).encode())
        text = body.get("messages", [{}])[-1].get("content", "")
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": text}}]})
    return handler


def test_provider_rules_from_toml(tmp_path):
    file = tmp_path / "veu.toml"
    file.write_text(textwrap.dedent('''
        [provedores.ollama]
        anonimizar = false

        [provedores.groq]
        operador = "mascara"
        bloquear = ["CARTAO_CREDITO"]
    '''), encoding="utf-8")
    config = load_config(file, environ={})
    assert config.providers["ollama"].url == "http://localhost:11434" and not config.providers["ollama"].anonymize
    seen = []
    app = create_app(config, upstream_transport=httpx.MockTransport(echo(seen)))
    call(app, "POST", "/ollama/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": PII}]})
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == PII  # local: sem anonimizar
    masked = call(app, "POST", "/groq/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": PII}]})
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == "Sou a M*** S***, CPF ***.982.247-**."
    assert masked.status_code == 200
    blocked = call(app, "POST", "/groq/v1/chat/completions",
                   json={"model": "m", "messages": [{"role": "user", "content": "cartão 4111 1111 1111 1111"}]})
    assert blocked.status_code == 400
    allowed = call(app, "POST", "/v1/chat/completions",
                   json={"model": "m", "messages": [{"role": "user", "content": "cartão 4111 1111 1111 1111"}]})
    assert allowed.status_code == 200


def test_operator_header_and_ollama_stream_through_proxy():
    seen = []
    app = create_app(Config(), upstream_transport=httpx.MockTransport(echo(seen)))
    call(app, "POST", "/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": PII}]},
         headers={"X-Veu-Operador": "remover"})
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == "Sou a [PESSOA], CPF [CPF]."
    assert call(app, "POST", "/v1/chat/completions", json={"model": "m", "messages": []},
                headers={"X-Veu-Operador": "xyz"}).status_code == 400
    response = call(app, "POST", "/api/chat", json={"model": "m", "messages": [{"role": "user", "content": PII}]})
    assert "Olá Maria Souza" in response.text and str(seen[-1].url) == "http://localhost:11434/api/chat"
    locked = create_app(Config(request_operator=False), upstream_transport=httpx.MockTransport(echo(seen)))
    call(locked, "POST", "/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": PII}]},
         headers={"X-Veu-Operador": "remover"})
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == "Sou a [PESSOA_1], CPF [CPF_1]."


def test_prometheus_metrics():
    seen = []
    app = create_app(Config(token="t", host="0.0.0.0"), upstream_transport=httpx.MockTransport(echo(seen)))
    call(app, "POST", "/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": PII}]},
         headers={"X-Veu-Token": "t"})
    assert call(app, "GET", "/veu/metricas").status_code == 401
    text = call(app, "GET", "/veu/metricas", headers={"Authorization": "Bearer t"}).text
    assert 'veu_requisicoes_total{provedor="openai"} 1' in text
    assert 'veu_dados_escondidos_total{entidade="CPF"} 1' in text
    assert "529" not in text
    disabled_seen = []
    disabled = create_app(Config(metrics=False), upstream_transport=httpx.MockTransport(echo(disabled_seen)))
    response = call(disabled, "GET", "/veu/metricas")
    assert response.status_code == 404 and not disabled_seen  # nunca vai para o provedor


# Arquivos e relatórios ---------------------------------------------------------------------------------------------

def test_cli_csv_with_forced_columns_and_restore(tmp_path, capsys):
    source = tmp_path / "clientes.csv"
    source.write_text("nome;cpf;obs\nJoana Prado;52998224725;ligar (11) 91234-5678\nCarlos Lima;99999999999;ok\n",
                      encoding="utf-8")
    vault = tmp_path / "cofre.json"
    output = tmp_path / "anonimo.csv"
    assert main(["anonimizar", str(source), "--forcar", "cpf=CPF", "--cofre", str(vault), "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == (
        "nome;cpf;obs\n[PESSOA_1];[CPF_1];ligar [TELEFONE_1]\n[PESSOA_2];[CPF_2];ok\n"
    )
    restored = tmp_path / "restaurado.csv"
    assert main(["restaurar", str(output), "--cofre", str(vault), "-o", str(restored)]) == 0
    assert restored.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_cli_jsonl_only_selected_fields(tmp_path):
    source = tmp_path / "conversas.jsonl"
    source.write_text('{"id": "529.982.247-25", "texto": "CPF 529.982.247-25"}\n', encoding="utf-8")
    output = tmp_path / "saida.jsonl"
    assert main(["anonimizar", str(source), "--campos", "texto", "-o", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {"id": "529.982.247-25", "texto": "CPF [CPF_1]"}


def test_reports_never_contain_full_values(tmp_path):
    findings = check_text('cpf = "529.982.247-25"\n', "app/config.py", Veu())
    for report_format in ("texto", "github", "json", "sarif"):
        assert "529.982.247-25" not in render(findings, report_format)
    assert render(findings, "github").startswith("::error file=app/config.py,line=1,col=8,title=Véu CPF::")
    document = sarif(findings)
    assert document["version"] == "2.1.0"
    result = document["runs"][0]["results"][0]
    assert result["ruleId"] == "CPF" and result["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    target = tmp_path / "a.py"
    target.write_text('cpf = "529.982.247-25"\n', encoding="utf-8")
    report = tmp_path / "veu.sarif"
    assert main(["verificar", str(target), "--formato", "github", "--sarif", str(report), "--nao-falhar"]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["runs"][0]["results"]


def test_action_definition_is_valid():
    yaml = pytest.importorskip("yaml")
    from pathlib import Path

    action = yaml.safe_load((Path(__file__).parent.parent / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert {"caminhos", "limiar", "sarif", "falhar"} <= set(action["inputs"])


def test_azure_style_provider_route():
    from veu.config import ProviderConfig

    config = Config()
    config = config.with_overrides(providers={**config.providers,
                                              "azure": ProviderConfig("azure", "openai", "https://recurso.openai.azure.com")})
    seen = []
    app = create_app(config, upstream_transport=httpx.MockTransport(echo(seen)))
    call(app, "POST", "/azure/openai/deployments/gpt/chat/completions?api-version=2024-10-21",
         json={"messages": [{"role": "user", "content": PII}]}, headers={"api-key": "k"})
    assert str(seen[-1].url) == "https://recurso.openai.azure.com/openai/deployments/gpt/chat/completions?api-version=2024-10-21"
    assert seen[-1].headers["api-key"] == "k"
    assert json.loads(seen[-1].content)["messages"][-1]["content"] == "Sou a [PESSOA_1], CPF [CPF_1]."
