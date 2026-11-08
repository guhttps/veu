"""Gateway para empresas: cofre cifrado, restaurações contadas e limitadas, âncora da auditoria e SSRF."""

import asyncio
import json
import os
import socket

import httpx
import pytest

from veu.cli import main
from veu.config import Config, ConfigError
from veu.server import create_app
from veu.server.state import AuditLog, RedisSessionStore, VaultCipher, audit_anchor, verify_audit
from veu.vault import Vault

CPF = "529.982.247-25"


def test_redis_requires_a_vault_key():
    with pytest.raises(ConfigError, match="VEU_CHAVE_COFRE"):
        Config(session_backend="redis://cache:6379/0")
    Config(session_backend="redis://cache:6379/0", allow_plain_vault=True)
    with pytest.raises(ConfigError, match="32 caracteres"):
        Config(session_backend="redis://cache:6379/0", vault_key="curta")


def test_vault_cipher_binds_to_session_and_detects_tampering():
    cipher = VaultCipher("k" * 32)
    blob = cipher.seal(b'{"itens": []}', "veu:proxy:a")
    assert cipher.open(blob, "veu:proxy:a") == b'{"itens": []}'
    assert cipher.open(blob, "veu:proxy:b") is None              # copiado para outra sessão
    assert cipher.open(blob[:-1] + bytes([blob[-1] ^ 1]), "veu:proxy:a") is None  # alterado
    assert VaultCipher("x" * 32).open(blob, "veu:proxy:a") is None   # outra chave
    assert cipher.open(b'{"itens": []}', "veu:proxy:a") is None      # sem cifra


def test_redis_store_ignores_plain_or_foreign_blobs():
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeRedis()
    store = RedisSessionStore("redis://x", Vault, client=client, cipher=VaultCipher("k" * 32))
    vault = store.get("s1")
    vault.placeholder("CPF", CPF)
    store._save("s1", vault)
    assert store.get("s1", create=False).restore("[CPF_1]") == CPF
    client.set("veu:sessao:s2", json.dumps(vault.to_dict()))  # alguém gravou um cofre em texto puro
    assert store.get("s2", create=False) is None


def upstream_echo(request):
    body = json.loads(request.content)
    text = " ".join(f"[CPF_{n}]" for n in range(1, 6))
    return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": f"{text} {body['model']}"}}]})


def post(app, content):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            response = await c.post("/v1/chat/completions", json={"model": "m", "messages": [
                {"role": "user", "content": content}]}, headers={"Authorization": "Bearer x"})
            stats = (await c.get("/veu/estatisticas")).json()
            return response, stats

    return asyncio.run(run())


CPFS = "529.982.247-25, 111.444.777-35, 123.456.789-09, 935.411.347-80, 714.602.380-01"


def test_restorations_are_counted_in_the_audit_log(tmp_path):
    log = tmp_path / "auditoria.jsonl"
    app = create_app(Config(audit_log=str(log)), upstream_transport=httpx.MockTransport(upstream_echo))
    response, stats = post(app, f"CPFs: {CPFS}")
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["restaurados"] == {"CPF": 5} and stats["dados_restaurados"] == 5
    assert "529.982.247-25" not in log.read_text(encoding="utf-8")


def test_max_restorations_per_response():
    app = create_app(Config(restore_max_per_response=2), upstream_transport=httpx.MockTransport(upstream_echo))
    response, _ = post(app, f"CPFs: {CPFS}")
    content = response.json()["choices"][0]["message"]["content"]
    assert content.count("[CPF_") == 3 and "529.982.247-25" in content


def test_audit_anchor(tmp_path, capsys, monkeypatch):
    path = tmp_path / "auditoria.jsonl"
    log = AuditLog(str(path), secret="s" * 32)
    for status in (200, 200, 500):
        log.write(status=status)
    anchor = audit_anchor(path, "s" * 32)
    assert anchor["registros"] == 3
    assert verify_audit(path, "s" * 32, anchor["hash"])[0]
    log.write(status=200)
    assert verify_audit(path, "s" * 32, anchor["hash"])[0]  # linhas novas depois da âncora: tudo certo
    # Apagar as últimas linhas (inclusive a ancorada) deixa uma cadeia íntegra, mas sem a âncora.
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:2]), encoding="utf-8")
    ok, _, problem = verify_audit(path, "s" * 32, anchor["hash"])
    assert not ok and "âncora" in problem
    monkeypatch.setenv("SEGREDO_TESTE", "s" * 32)
    assert main(["auditoria", "ancorar", str(path), "--segredo-env", "SEGREDO_TESTE"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["registros"] == 2


def test_anchor_of_an_empty_log(tmp_path):
    # Logo depois de implantar, ainda sem requisições: não há o que ancorar (antes saía uma âncora que nunca conferia).
    path = tmp_path / "auditoria.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="ainda não tem registros"):
        audit_anchor(path)
    AuditLog(str(path)).write(status=200)
    assert verify_audit(path, None, "0" * 64)[0]  # âncoras antigas do log vazio (o começo da cadeia) conferem


@pytest.mark.parametrize("address", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "::1", "100.64.0.1"])
def test_link_reading_refuses_internal_addresses(monkeypatch, address):
    from veu.sources import _PUBLIC_ONLY, SourceError, check_public_url

    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(family, 1, 6, "", (address, 443))])
    with pytest.raises(SourceError, match="interno"):
        check_public_url("https://docs.google.com/document/d/x")
    token = _PUBLIC_ONLY.set(True)
    try:
        from veu.sources import _SafeRedirect

        with pytest.raises(SourceError):
            _SafeRedirect().redirect_request(None, None, 302, "Found", {}, "https://interno.example/meta")
    finally:
        _PUBLIC_ONLY.reset(token)


def test_link_reading_needs_https_and_public_address(monkeypatch):
    from veu.sources import SourceError, check_public_url

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("142.250.0.1", 443))])
    check_public_url("https://docs.google.com/document/d/x")
    with pytest.raises(SourceError, match="https"):
        check_public_url("http://docs.google.com/document/d/x")


def test_link_expander_turns_on_public_only():
    from veu.sources import _PUBLIC_ONLY, Document, LinkExpander

    seen = []

    def reader(url):
        seen.append(_PUBLIC_ONLY.get())
        return Document(url, "t", "conteúdo", "web")

    expander = LinkExpander(reader=reader)
    expander.expand_with_known("veja https://docs.google.com/document/d/abc")
    assert seen == [True] and _PUBLIC_ONLY.get() is False


def test_workers_need_shared_sessions(monkeypatch):
    from veu.server import app as server

    with pytest.raises(ConfigError, match="Redis"):
        server.run(Config(), workers=2)


def test_workers_get_the_profile_from_the_command_line(monkeypatch):
    import sys
    import types

    from veu.server import app as server

    for name in ("VEU_PERFIL", "VEU_HOST", "VEU_PORTA"):
        monkeypatch.setenv(name, "")  # o monkeypatch devolve os valores originais no fim
    calls = []
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda *a, **k: calls.append((a, k))))
    monkeypatch.setattr(server, "create_app", lambda config, **kw: object())
    config = Config(session_backend="redis://cache:6379/0", allow_plain_vault=True).with_profile("setor-publico")
    server.run(config, workers=2)
    assert calls and calls[0][1]["workers"] == 2
    assert os.environ["VEU_PERFIL"] == "setor-publico"  # veu servir --perfil setor-publico --workers 2
    assert server.load_config(None, environ=dict(os.environ)).profile == "setor-publico"


def test_each_worker_writes_its_own_audit_chain(monkeypatch, tmp_path):
    import os

    from veu.server import app as server

    monkeypatch.setenv("VEU_LOG_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.delenv("VEU_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    created = []
    monkeypatch.setattr(server, "create_app", lambda config, **kw: created.append(config) or object())
    server.app_from_environment()
    assert created[0].audit_log.endswith(f"auditoria.{os.getpid()}.jsonl")
