"""Ganchos para Claude Code e Cursor, plugin do Claude Code e skill."""

import io
import json
import shlex
from pathlib import Path

import pytest

from veu.cli import build_parser, main
from veu.hooks import run

ROOT = Path(__file__).resolve().parent.parent
SECRET = "sk-" + "proj-" + "aB3" * 12  # montada em pedaços: não é uma chave real


def hook(event, payload, capsys, **options):
    code = run(event, stdin=io.StringIO(json.dumps(payload)), **options)
    out, err = capsys.readouterr()
    return code, (json.loads(out) if out.strip() else None), err


def test_prompt_with_secret_is_blocked(capsys):
    code, out, err = hook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": f"use {SECRET}"}, capsys)
    assert code == 2 and "Chave de API" in err and SECRET not in err and out is None


def test_prompt_with_personal_data_warns_or_blocks(capsys):
    payload = {"prompt": "Cliente Maria Souza, CPF 529.982.247-25"}
    code, out, err = hook("prompt", payload, capsys)
    assert code == 0 and "CPF" in out["systemMessage"] and "529.982" not in out["systemMessage"]
    code, out, err = hook("prompt", payload, capsys, mode="bloquear")
    assert code == 2 and "CPF" in err
    code, out, err = hook("prompt", {"prompt": "Refatore a função de login"}, capsys)
    assert (code, out, err) == (0, None, "")


def test_file_with_secret_is_denied_with_suggestion(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(f"OPENAI_API_KEY={SECRET}\nDEBUG=true\n", encoding="utf-8")
    code, out, _ = hook("arquivo", {"tool_name": "Read", "tool_input": {"file_path": str(env)}}, capsys)
    decision = out["hookSpecificOutput"]
    assert code == 0 and decision["permissionDecision"] == "deny"
    assert "ler_protegido" in decision["permissionDecisionReason"] and SECRET not in json.dumps(out)


def test_file_with_personal_data_asks_and_options(tmp_path, capsys):
    file = tmp_path / "clientes.csv"
    file.write_text("nome,cpf\nMaria Souza,529.982.247-25\n", encoding="utf-8")
    payload = {"tool_input": {"file_path": str(file)}}
    _, out, _ = hook("arquivo", payload, capsys)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    _, out, _ = hook("arquivo", payload, capsys, pii="negar")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hook("arquivo", payload, capsys, pii="permitir")[1] is None
    code, out, _ = hook("arquivo", {"tool_input": {"file_path": str(tmp_path / "nao-existe.txt")}}, capsys)
    assert (code, out) == (0, None)


def test_cursor_format(tmp_path, capsys):
    _, out, _ = hook("prompt", {"prompt": f"chave {SECRET}"}, capsys, fmt="cursor")
    assert out["continue"] is False and "Chave de API" in out["userMessage"]
    _, out, _ = hook("arquivo", {"file_path": "x.env", "content": f"TOKEN={SECRET}"}, capsys, fmt="cursor")
    assert out["permission"] == "deny"
    _, out, _ = hook("arquivo", {"file_path": "x.py", "content": "print('oi')"}, capsys, fmt="cursor")
    assert out == {"permission": "allow"}


def test_cli_gancho(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": f"use {SECRET}"})))
    assert main(["gancho", "prompt"]) == 2
    assert "Chave de API" in capsys.readouterr().err


def test_plugin_files_are_consistent():
    plugin = ROOT / "plugin"
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    from veu import __version__

    assert manifest["version"] == __version__ == marketplace["plugins"][0]["version"]
    assert marketplace["plugins"][0]["source"] == "./plugin"
    hooks = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    commands = [h["command"] for group in hooks.values() for entry in group for h in entry["hooks"]]
    cursor = json.loads((ROOT / "examples" / "cursor-hooks.json").read_text(encoding="utf-8"))["hooks"]
    commands += [h["command"] for group in cursor.values() for h in group]
    parser = build_parser()
    for command in commands:
        argv = shlex.split(command)
        assert argv[0] == "veu"
        parser.parse_args(argv[1:])  # o comando existe e as opções são válidas
    mcp = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["veu"]
    assert [mcp["command"], *mcp["args"]] == ["veu", "mcp"]
    skill = (plugin / "skills" / "protecao-de-dados" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: protecao-de-dados\ndescription: ")
    for tool in ("ler_protegido", "verificar_arquivo", "anonimizar_arquivo", "restaurar_para_arquivo"):
        assert tool in skill


@pytest.mark.parametrize("tool", ["ler_protegido", "verificar_arquivo", "anonimizar_arquivo", "anonimizar_texto",
                                  "restaurar_para_arquivo"])
def test_skill_tools_exist_in_mcp(tool):
    pytest.importorskip("mcp")
    import asyncio

    from mcp.client import Client

    from veu.integrations.mcp import build_server

    async def names():
        async with Client(build_server()) as client:
            return {item.name for item in (await client.list_tools()).tools}

    assert tool in asyncio.run(names())
