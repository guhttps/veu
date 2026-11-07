"""Recursos para empresas: equipes com token, auditoria encadeada, sessões no Redis, desvio e prontidão."""

import json

import httpx
import pytest
from test_server import Upstream, call, chat

from veu.cli import main
from veu.config import Config, ConfigError, ProviderConfig, TeamConfig, load_config
from veu.server import create_app
from veu.server.state import AuditLog, verify_audit

CPF = "529.982.247-25"
PII = f"Sou o Carlos Souza, CPF {CPF}."


def app_with(upstream, **options):
    return create_app(Config(**options), upstream_transport=httpx.MockTransport(upstream))


# Equipes ----------------------------------------------------------------------------------------------------------

def test_team_tokens_identify_and_apply_policy(tmp_path):
    upstream = Upstream()
    log = tmp_path / "auditoria.jsonl"
    teams = {
        "juridico": TeamConfig("juridico", "token-juridico", block=("CPF",)),
        "rh": TeamConfig("rh", "token-rh"),
    }
    app = app_with(upstream, teams=teams, audit_log=str(log))
    assert call(app, "POST", "/v1/chat/completions", json=chat(PII)).status_code == 401
    assert call(app, "POST", "/v1/chat/completions", json=chat(PII), headers={"x-veu-token": "errado"}).status_code == 401
    ok = call(app, "POST", "/v1/chat/completions", json=chat(PII), headers={"x-veu-token": "token-rh"})
    assert ok.status_code == 200 and CPF in ok.json()["choices"][0]["message"]["content"]
    blocked = call(app, "POST", "/v1/chat/completions", json=chat(PII), headers={"x-veu-token": "token-juridico"})
    assert blocked.status_code == 400 and blocked.headers["x-veu-bloqueado"] == "CPF"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r.get("equipe") for r in records] == ["rh", "juridico"]
    metrics = call(app, "GET", "/veu/metricas", headers={"x-veu-token": "token-rh"}).text
    assert 'veu_requisicoes_por_equipe_total{equipe="rh"} 1' in metrics


def test_exposed_server_with_only_team_tokens_starts():
    create_app(Config(host="0.0.0.0", teams={"rh": TeamConfig("rh", "t")}))
    with pytest.raises(ConfigError):
        create_app(Config(host="0.0.0.0"))


def test_teams_from_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_JURIDICO", "abc")
    path = tmp_path / "veu.toml"
    path.write_text(
        '[equipes.juridico]\ntoken_env = "TOKEN_JURIDICO"\nbloquear = ["cpf"]\noperador = "mascara"\n'
        '[politica]\ndesviar_para = "ollama"\nmodelo_desvio = "llama3.1"\ndesviar_tipos = ["cpf"]\n'
        '[servidor]\nsessoes = "redis://cache:6379/0"\nsegredo_auditoria_env = "SEGREDO_AUD"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SEGREDO_AUD", "s3" * 16)
    config = load_config(str(path))
    assert config.teams["juridico"] == TeamConfig("juridico", "abc", ("CPF",), "mascara")
    assert (config.route_to, config.route_model, config.route_labels) == ("ollama", "llama3.1", ("CPF",))
    assert config.session_backend == "redis://cache:6379/0" and config.audit_secret == "s3" * 16
    monkeypatch.delenv("TOKEN_JURIDICO")
    with pytest.raises(ConfigError, match="sem token"):
        load_config(str(path))


# Auditoria --------------------------------------------------------------------------------------------------------

def test_audit_chain_detects_changes_and_removals(tmp_path):
    path = tmp_path / "auditoria.jsonl"
    log = AuditLog(str(path), secret="segredo")
    for status in (200, 400, 200):
        log.write(provedor="openai", status=status, entidades={"CPF": 1})
    assert verify_audit(path, "segredo") == (True, 3, None)
    assert not verify_audit(path, "outro")[0]
    # Continua a cadeia depois de reiniciar.
    AuditLog(str(path), secret="segredo").write(provedor="openai", status=200)
    assert verify_audit(path, "segredo") == (True, 4, None)

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = lines[:]
    tampered[1] = tampered[1].replace('"status": 400', '"status": 200')
    path.write_text("\n".join(tampered) + "\n", encoding="utf-8")
    ok, _, problem = verify_audit(path, "segredo")
    assert not ok and "linha 2" in problem and "alterado" in problem

    path.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
    ok, _, problem = verify_audit(path, "segredo")
    assert not ok and "cadeia" in problem


def test_cli_auditoria_verificar(tmp_path, capsys, monkeypatch):
    path = tmp_path / "a.jsonl"
    AuditLog(str(path)).write(status=200)
    assert main(["auditoria", "verificar", str(path)]) == 0
    assert "íntegro" in capsys.readouterr().out
    path.write_text(path.read_text(encoding="utf-8").replace("200", "500"), encoding="utf-8")
    assert main(["auditoria", "verificar", str(path)]) == 1


# Sessões no Redis (duas réplicas) ---------------------------------------------------------------------------------

def test_redis_sessions_shared_between_replicas(monkeypatch):
    fakeredis = pytest.importorskip("fakeredis")
    import redis

    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda *a, **k: fakeredis.FakeRedis(server=server)))
    first, second = Upstream(), Upstream()
    replica_a = app_with(first, session_backend="redis://cache:6379/0")
    replica_b = app_with(second, session_backend="redis://cache:6379/0")
    headers = {"x-veu-sessao": "conversa-1", "authorization": "Bearer chave"}

    call(replica_a, "POST", "/v1/chat/completions", json=chat(f"CPF {CPF}"), headers=headers)
    assert "[CPF_1]" in json.dumps(first.last_body)
    response = call(replica_b, "POST", "/v1/chat/completions", json=chat("outro CPF 111.444.777-35"), headers=headers)
    assert "[CPF_2]" in json.dumps(second.last_body)  # a numeração continua na outra réplica
    assert CPF in response.json()["choices"][0]["message"]["content"]  # e restaura o [CPF_1] da primeira
    assert call(replica_b, "GET", "/veu/pronto").status_code == 200
    stored = [key for key in fakeredis.FakeRedis(server=server).scan_iter() if b"trava" not in key]
    assert stored and all(fakeredis.FakeRedis(server=server).ttl(key) > 0 for key in stored)


def test_ready_fails_when_store_is_down(monkeypatch):
    app = app_with(Upstream())
    assert call(app, "GET", "/veu/pronto").json()["status"] == "pronto"


# Desvio para um modelo interno ------------------------------------------------------------------------------------

def test_route_sensitive_requests_to_internal_provider(monkeypatch):
    upstream = Upstream()
    providers = {**Config().providers, "interno": ProviderConfig("interno", "openai", "http://ia.interna.example/v1",
                                                                 "CHAVE_INTERNA")}
    monkeypatch.setenv("CHAVE_INTERNA", "segredo-interno")
    app = app_with(upstream, providers=providers, route_to="interno", route_model="llama3.1", route_labels=("CPF",))

    call(app, "POST", "/v1/chat/completions", json=chat(PII), headers={"authorization": "Bearer chave-openai"})
    routed = upstream.requests[-1]
    assert routed.url.host == "ia.interna.example" and routed.url.path == "/v1/chat/completions"
    assert CPF in routed.content.decode() and json.loads(routed.content)["model"] == "llama3.1"
    assert routed.headers["authorization"] == "Bearer segredo-interno"  # a chave da OpenAI não vai para lá

    call(app, "POST", "/v1/chat/completions", json=chat("Oi, sou o Carlos Souza"))
    normal = upstream.requests[-1]
    assert normal.url.host == "api.openai.com" and "[PESSOA_1]" in normal.content.decode()
    stats = call(app, "GET", "/veu/estatisticas").json()
    assert stats["desviadas"] == 1


def test_route_config_validation():
    with pytest.raises(ConfigError, match="desviar_para"):
        Config(route_to="nao-existe")
    with pytest.raises(ConfigError, match="sessoes"):
        Config(session_backend="mysql://x")


# Arquivos de implantação ------------------------------------------------------------------------------------------

def test_deploy_configs_load(monkeypatch, tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for name in ("VEU_TOKEN", "VEU_TOKEN_ATENDIMENTO", "VEU_TOKEN_JURIDICO", "VEU_SEGREDO_AUDITORIA"):
        monkeypatch.setenv(name, f"valor-{name.lower()}".ljust(32, "x"))
    config = load_config(str(root / "deploy" / "veu-empresa.toml"))
    assert set(config.teams) == {"atendimento", "juridico"} and config.audit_secret
    create_app(config)  # fora do localhost, com token: inicia

    values = (root / "deploy" / "helm" / "veu" / "values.yaml").read_text(encoding="utf-8")
    block = values.split("config: |\n", 1)[1].split("\n\n# ", 1)[0]
    toml = "\n".join(line[2:] for line in block.splitlines())
    path = tmp_path / "helm.toml"
    path.write_text(toml, encoding="utf-8")
    helm = load_config(str(path))
    assert helm.audit_log == "-" and helm.inject_keys and "segredos" in helm.detectors


def test_demonstrar(capsys):
    assert main(["demonstrar"]) == 0
    output = capsys.readouterr().out
    assert output.count("VAZOU") == 7 and "nenhum valor chegou ao provedor" in output
    assert output.count("bloqueado") == 3 and "desarmado" in output and "NÃO" not in output


def test_demonstrar_fails_when_restoration_is_unsafe(capsys, monkeypatch):
    from veu.vault import RestorePolicy

    monkeypatch.setattr(RestorePolicy, "allows", lambda self, label, before, *, tool: True)
    assert main(["demonstrar"]) == 1
    output = capsys.readouterr().out
    assert output.count("VAZOU") == 7 + 3 and "problema(s)" in output


def test_demonstrar_negative_control(capsys, monkeypatch):
    from veu import demo

    original = demo._request
    monkeypatch.setattr(demo, "_request", lambda: {**original(), "messages": original()["messages"][:1]})
    assert main(["demonstrar"]) == 3
    assert "Controle falhou" in capsys.readouterr().out
