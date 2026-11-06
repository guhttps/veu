"""Painel do Véu (veu painel), atalhos e instalador: o caminho para quem não programa."""

import json
import sys
import tomllib
from pathlib import Path

import httpx
import pytest
from test_server import Upstream, call

from veu import atalhos
from veu.config import Config, load_config
from veu.server import create_app
from veu.server import panel as panel_module
from veu.server.panel import PanelController, apply_settings, dump_toml, settings_from_config

CPF = "529.982.247-25"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def panel_app(tmp_path, monkeypatch):
    monkeypatch.setattr(atalhos, "autostart_enabled", lambda: False)
    controller = PanelController(tmp_path / "veu.toml")
    app = create_app(Config(), upstream_transport=httpx.MockTransport(Upstream()), panel=controller)
    return app, controller


def test_page_and_state(panel_app):
    app, controller = panel_app
    page = call(app, "GET", "/veu/painel")
    assert page.status_code == 200 and "Proteger um arquivo" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert call(app, "GET", "/").headers["location"] == "/veu/painel"
    state = call(app, "GET", "/veu/painel/estado").json()
    assert state["configuracoes"]["categorias"] == list(panel_module.CATEGORIES)
    assert state["endereco"] == "http://127.0.0.1:8787" and set(state["aplicativos"]) == {"claude", "cursor"}


def test_panel_routes_only_exist_in_panel_mode():
    app = create_app(Config(), upstream_transport=httpx.MockTransport(Upstream()))
    assert call(app, "GET", "/veu/painel").status_code == 404
    assert call(app, "POST", "/veu/painel/desligar").status_code == 404


def test_other_sites_cannot_change_settings(panel_app):
    app, controller = panel_app
    response = call(app, "POST", "/veu/painel/configuracoes", json={"categorias": ["documentos"]},
                    headers={"origin": "https://site-malicioso.example"})
    assert response.status_code == 403 and not controller.config_path.exists()


def test_save_settings_writes_toml_and_restarts(panel_app):
    app, controller = panel_app
    controller.config_path.write_text('[servidor]\nporta = 9000\n\n[[deteccao.personalizados]]\nentidade = "MATRICULA"\n'
                                      'padrao = "MAT-\\\\d{6}"\n', encoding="utf-8")
    response = call(app, "POST", "/veu/painel/configuracoes", json={
        "categorias": ["documentos", "financeiro"], "bloquear": ["cartoes", "chaves_privadas"],
        "operador": "sintetico", "ignorar": ["contato@empresa.example", "  ", "11.222.333/0001-81"],
    })
    assert response.json() == {"ok": True, "reiniciando": True} and controller.restart
    config = load_config(controller.config_path, environ={})
    assert config.port == 9000 and config.custom_patterns[0]["entidade"] == "MATRICULA"  # o resto ficou
    assert "CPF" in config.labels and "PESSOA" not in config.labels and "CARTAO_CREDITO" in config.labels
    assert set(config.block) == {"CARTAO_CREDITO", "CHAVE_PRIVADA"} and config.operator == "sintetico"
    assert config.allowlist == ("contato@empresa.example", "11.222.333/0001-81")
    assert settings_from_config(config) == {
        "categorias": ["documentos", "financeiro"], "ignorar": ["contato@empresa.example", "11.222.333/0001-81"],
        "bloquear": ["chaves_privadas", "cartoes"], "operador": "sintetico",
    }
    bad = call(app, "POST", "/veu/painel/configuracoes", json={"categorias": []})
    assert bad.status_code == 400 and "pelo menos um" in bad.json()["error"]["message"]


def test_all_categories_means_every_type(tmp_path):
    path = tmp_path / "veu.toml"
    apply_settings(path, {"categorias": list(panel_module.CATEGORIES), "operador": "token"})
    assert load_config(path, environ={}).labels == ()


def test_dump_toml_round_trip():
    data = {
        "deteccao": {"limiar": 0.6, "entidades": ["CPF"], "personalizados": [{"entidade": "X", "padrao": "a\\d"}]},
        "servidor": {"porta": 8787, "playground": False, "nome com espaço": "é"},
        "equipes": {"juridico": {"token_env": "T", "bloquear": ["CPF"]}},
    }
    assert tomllib.loads(dump_toml(data)) == data


def test_protect_and_restore_spreadsheet(panel_app):
    openpyxl = pytest.importorskip("openpyxl")
    import io

    app, _ = panel_app
    workbook = openpyxl.Workbook()
    workbook.active.append(["nome", "cpf", "obs"])
    workbook.active.append(["Maria Souza", CPF, "ligar (11) 98765-4321"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    protected = call(app, "POST", "/veu/painel/arquivos/proteger?nome=clientes.xlsx", content=buffer.getvalue())
    assert protected.status_code == 200
    assert "clientes-protegido.xlsx" in protected.headers["content-disposition"]
    assert json.loads(protected.headers["x-veu-escondidos"]) == {"PESSOA": 1, "CPF": 1, "TELEFONE": 1}
    row = [cell.value for cell in openpyxl.load_workbook(io.BytesIO(protected.content)).active[2]]
    assert row == ["[PESSOA_1]", "[CPF_1]", "ligar [TELEFONE_1]"]

    session = protected.headers["x-veu-sessao"]
    restored = call(app, "POST", f"/veu/painel/arquivos/restaurar?nome=clientes-protegido.xlsx&sessao={session}",
                    content=protected.content)
    assert "clientes-com-dados.xlsx" in restored.headers["content-disposition"]
    assert [cell.value for cell in openpyxl.load_workbook(io.BytesIO(restored.content)).active[2]] == \
        ["Maria Souza", CPF, "ligar (11) 98765-4321"]
    stats = call(app, "GET", "/veu/painel/estado").json()["estatisticas"]
    assert stats["dados_escondidos"] == 3


def test_text_files_pdf_and_errors(panel_app):
    app, _ = panel_app
    text = call(app, "POST", "/veu/painel/arquivos/proteger?nome=nota.txt", content=f"CPF {CPF}".encode())
    assert text.content == b"CPF [CPF_1]"
    unsupported = call(app, "POST", "/veu/painel/arquivos/proteger?nome=foto.png", content=b"\x89PNG")
    assert unsupported.status_code == 400 and "Formato" in unsupported.json()["error"]["message"]
    missing = call(app, "POST", "/veu/painel/arquivos/restaurar?nome=nota.txt&sessao=nao-existe", content=b"x")
    assert missing.status_code == 404
    pytest.importorskip("pypdf")
    from test_sources import minimal_pdf

    pdf = call(app, "POST", "/veu/painel/arquivos/proteger?nome=laudo.pdf", content=minimal_pdf(f"Paciente CPF {CPF}"))
    assert pdf.status_code == 200 and "laudo-protegido.txt" in pdf.headers["content-disposition"]
    assert b"[CPF_1]" in pdf.content and CPF.encode() not in pdf.content


def test_connect_claude_desktop_keeps_other_servers(panel_app, tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    app, _ = panel_app
    folder = tmp_path / "Claude"
    folder.mkdir()
    config_file = folder / "claude_desktop_config.json"
    config_file.write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}, "tema": "escuro"}), encoding="utf-8")
    apps = {"claude": {"titulo": "Claude Desktop", "arquivo": config_file, "pasta": folder},
            "cursor": {"titulo": "Cursor", "arquivo": tmp_path / ".cursor" / "mcp.json", "pasta": tmp_path / ".cursor"}}
    monkeypatch.setattr(panel_module, "mcp_apps", lambda: apps)

    status = call(app, "POST", "/veu/painel/aplicativos/claude", json={"conectar": True}).json()
    assert status == {"titulo": "Claude Desktop", "instalado": True, "conectado": True}
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["tema"] == "escuro" and "outro" in saved["mcpServers"]
    assert saved["mcpServers"]["veu"]["args"][-1] == "mcp"
    assert (folder / "claude_desktop_config.json.antes-do-veu").is_file()

    cursor = call(app, "POST", "/veu/painel/aplicativos/cursor", json={"conectar": True}).json()
    assert cursor["conectado"]  # cria o arquivo mesmo antes de o Cursor ser instalado
    off = call(app, "POST", "/veu/painel/aplicativos/claude", json={"conectar": False}).json()
    assert not off["conectado"] and "outro" in json.loads(config_file.read_text(encoding="utf-8"))["mcpServers"]
    assert call(app, "POST", "/veu/painel/aplicativos/chatgpt", json={}).status_code == 404


def test_startup_toggle_and_shutdown(panel_app, monkeypatch):
    app, controller = panel_app
    calls = []
    monkeypatch.setattr(atalhos, "set_autostart", lambda enabled: calls.append(enabled))
    monkeypatch.setattr(atalhos, "autostart_enabled", lambda: bool(calls and calls[-1]))
    assert call(app, "POST", "/veu/painel/inicializacao", json={"ativo": True}).json() == {"inicializacao": True}
    assert calls == [True]
    assert call(app, "POST", "/veu/painel/desligar", json={}).json() == {"ok": True}
    assert controller.restart is False


# Atalhos ----------------------------------------------------------------------------------------------------------

def test_shortcuts_on_linux_and_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    (tmp_path / "Desktop").mkdir()
    monkeypatch.setattr(sys, "platform", "linux")
    created = atalhos.create_shortcuts()
    assert {path.name for path in created} == {"veu.desktop"} and len(created) == 2
    assert "painel" in created[0].read_text(encoding="utf-8")
    atalhos.set_autostart(True)
    assert atalhos.autostart_enabled() and "--sem-abrir" in atalhos._autostart_file().read_text(encoding="utf-8")
    atalhos.set_autostart(False)
    assert not atalhos.autostart_enabled()
    atalhos.create_shortcuts(remove=True)
    assert not any(path.exists() for path in created)

    monkeypatch.setattr(sys, "platform", "darwin")
    (tmp_path / "Applications").mkdir()
    created = atalhos.create_shortcuts()
    assert all(path.suffix == ".command" for path in created)
    atalhos.set_autostart(True)
    assert "<string>painel</string>" in atalhos._autostart_file().read_text(encoding="utf-8")


def test_veu_command_finds_the_installed_cli():
    command = atalhos.veu_command()
    assert Path(command[0]).exists() or command[1:] == ["-m", "veu"]
    assert Path(atalhos.icon_path()).is_file()


# Instaladores -----------------------------------------------------------------------------------------------------

def test_installers_install_the_right_extras():
    windows = (ROOT / "web" / "instalar.ps1").read_text(encoding="utf-8")
    unix = (ROOT / "web" / "instalar.sh").read_text(encoding="utf-8")
    for script in (windows, unix):
        assert "veu[servidor,mcp,documentos]" in script and "astral.sh/uv" in script
        assert "atalhos" in script and "painel" in script
    assert windows.isascii()  # o PowerShell 5.1 pode ler o script baixado com a codificação errada
