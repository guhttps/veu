"""Gancho de comando: Bash e Grep não podem ser um atalho para ler segredos que o Read bloquearia."""

import io
import json

import pytest

from veu import Veu
from veu.hooks import check_command, check_prompt, proxy_missing, run

veu = Veu()
KEY = "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".env").write_text(f"OPENAI_API_KEY={KEY}\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "secrets.yaml").write_text(f"token: {KEY}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Projeto de exemplo.\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('oi')\n", encoding="utf-8")
    return tmp_path


def decision(result):
    code, out, err = result
    if not out:
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def bash(command, cwd):
    return check_command({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}, veu)


@pytest.mark.parametrize("command", [
    "cat .env", "head -n 5 .env", "grep OPENAI .env", "less config/secrets.yaml", "cat ./.env | head",
    "printenv", "env", "printenv OPENAI_API_KEY", "echo $OPENAI_API_KEY", 'echo "${GITHUB_TOKEN}"',
    "Get-ChildItem env:", "Write-Output $env:OPENAI_API_KEY",
])
def test_blocks_commands_that_show_secrets(project, command):
    assert decision(bash(command, project)) == "deny"
    reason = json.loads(bash(command, project)[1])["hookSpecificOutput"]["permissionDecisionReason"]
    assert KEY not in reason


@pytest.mark.parametrize("command", [
    "cat README.md", "python app.py", "ls -la", "git status", "env PYTHONPATH=src pytest", 'test -n "$OPENAI_API_KEY"',
])
def test_allows_ordinary_commands(project, command):
    assert decision(bash(command, project)) == "allow"


def grep(project, **tool_input):
    return check_command({"tool_name": "Grep", "tool_input": {"pattern": "token", **tool_input}, "cwd": str(project)},
                         veu)


def test_grep_with_content_over_secret_files_is_blocked(project):
    assert decision(grep(project, output_mode="content")) == "deny"
    assert decision(grep(project, output_mode="content", path="config")) == "deny"
    assert decision(grep(project, output_mode="content", path=".env")) == "deny"


def test_grep_without_content_or_restricted_is_allowed(project):
    assert decision(grep(project)) == "allow"  # só nomes de arquivos
    assert decision(grep(project, output_mode="content", glob="*.py")) == "allow"
    assert decision(grep(project, output_mode="content", path="README.md")) == "allow"


def test_cursor_shell_format(project):
    code, out, _ = check_command({"command": "cat .env", "cwd": str(project)}, veu, fmt="cursor")
    assert code == 0 and json.loads(out)["permission"] == "deny"


def test_require_proxy():
    assert proxy_missing({}) is not None
    assert proxy_missing({"ANTHROPIC_BASE_URL": "http://localhost:8787"}) is None
    assert proxy_missing({"OPENAI_BASE_URL": "http://127.0.0.1:8787/v1"}) is None
    assert proxy_missing({"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}) is not None
    code, _, err = check_prompt({"prompt": "oi"}, veu, require_proxy=True, environ={})
    assert code == 2 and "proxy" in err
    assert check_prompt({"prompt": "oi"}, veu, require_proxy=True, environ={"ANTHROPIC_BASE_URL": "http://localhost:8787"})[0] == 0


def test_cli_entry(project, capsys):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat .env"}, "cwd": str(project)})
    assert run("comando", stdin=io.StringIO(payload)) == 0
    assert '"deny"' in capsys.readouterr().out


def test_plugin_hooks_cover_bash_and_grep():
    from pathlib import Path

    hooks = json.loads((Path(__file__).resolve().parent.parent / "plugin" / "hooks" / "hooks.json").read_text("utf-8"))
    matchers = {entry["matcher"]: entry["hooks"][0]["command"] for entry in hooks["hooks"]["PreToolUse"]}
    assert matchers == {"Read": "veu gancho arquivo", "Bash|Grep": "veu gancho comando"}
