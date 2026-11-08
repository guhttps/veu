"""Ganchos (hooks) para agentes de código: Claude Code e Cursor.

    veu gancho prompt     # antes de enviar o prompt: bloqueia segredos, avisa sobre dados pessoais
    veu gancho arquivo    # antes de o agente ler um arquivo (Read): bloqueia arquivos com segredos
    veu gancho comando    # antes de Bash e Grep: bloqueia "cat .env", "printenv" e buscas em arquivos com segredos

O Read não é o único caminho até um arquivo: o agente pode rodar "cat .env" no terminal ou buscar com o Grep e
receber as linhas. O gancho de comando cobre esses caminhos.

O agente recebe o motivo e a sugestão de usar a ferramenta MCP ler_protegido, que lê o arquivo com os dados
trocados por marcadores. Nenhum valor real aparece nas mensagens: só os tipos e as quantidades.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

from veu.core import Veu
from veu.entities import LABELS, SECRET_LABELS

MAX_FILE_BYTES = 2 * 1024 * 1024
FORMATS = ("claude", "cursor")
# Arquivos que costumam guardar segredos: o Grep com conteúdo num diretório passa por eles.
SECRET_FILES = re.compile(
    r"(?:^\.env(?:\..+)?|.+\.(?:pem|key|p12|pfx)|id_(?:rsa|dsa|ecdsa|ed25519)|credentials(?:\.json)?|\.npmrc|"
    r"\.pypirc|\.netrc|\.pgpass|secrets?\.(?:json|ya?ml|toml|env)|.*\.tfvars)$", re.IGNORECASE)
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build", ".cache"})
# Variáveis que costumam guardar segredos: echo $OPENAI_API_KEY, $env:GITHUB_TOKEN, ${DB_PASSWORD}.
SECRET_VARIABLE = re.compile(r"\$(?:env:)?\{?[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|SENHA|CREDENTIAL)"
                             r"[A-Za-z0-9_]*", re.IGNORECASE)
ENV_DUMP = frozenset({"env", "printenv", "set", "export", "declare", "typeset", "compgen"})
_SEGMENTS = re.compile(r"\|\||&&|[;|&\n]")
_PREFIXES = frozenset({"sudo", "command", "builtin", "exec", "nohup", "time"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")


def dumps_environment(command: str) -> bool:
    """O comando mostra as variáveis de ambiente (em qualquer trecho: depois de |, ;, && ou com o caminho completo)?

    env só despeja o ambiente quando não roda nenhum programa ("env | grep KEY", e não "env FOO=1 pytest").
    """
    if re.search(r"Get-ChildItem\s+env:|\b(?:gci|ls|dir)\s+env:|GetEnvironmentVariables", command, re.IGNORECASE):
        return True
    for segment in _SEGMENTS.split(command):
        words = segment.split()
        while words and words[0] in _PREFIXES:
            words = words[1:]
        if not words:
            continue
        name, rest = words[0].rsplit("/", 1)[-1], words[1:]
        if name not in ENV_DUMP:
            continue
        if name == "printenv":
            return True
        if name == "env":
            index = 0
            while index < len(rest) and (rest[index].startswith("-") or _ASSIGNMENT.fullmatch(rest[index])):
                index += 2 if rest[index] in ("-u", "-C", "-S", "--unset", "--chdir") else 1
            if index >= len(rest):
                return True
            continue
        # set, export, declare, typeset e compgen: sem argumentos, ou só com as opções que listam (-p, -x).
        if not rest or all(re.fullmatch(r"-[px]+", word) for word in rest):
            return True
    return False
# Endereços do proxy do Véu para --exigir-proxy.
PROXY_HOSTS = ("http://127.0.0.1:", "http://localhost:", "https://127.0.0.1:", "https://localhost:")


def _names(counts: Counter) -> str:
    return ", ".join(f"{count} {LABELS.get(label, label).split(' (')[0]}" for label, count in counts.most_common())


def _result(allow: bool, message: str, fmt: str, event: str, *, ask: bool = False) -> tuple[int, str, str]:
    """(código de saída, stdout, stderr) no formato de cada agente."""
    if fmt == "cursor":
        if event in ("arquivo", "comando"):
            payload: dict = {"permission": "ask" if ask else ("allow" if allow else "deny")}
        else:
            payload = {"continue": allow}
        if message:
            payload.update(userMessage=message, agentMessage=message)
        return 0, json.dumps(payload, ensure_ascii=False), ""
    if event in ("arquivo", "comando"):
        if allow and not ask:
            return 0, json.dumps({"systemMessage": message}, ensure_ascii=False) if message else "", ""
        decision = "ask" if ask else "deny"
        return 0, json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": message,
        }}, ensure_ascii=False), ""
    if not allow:
        return 2, "", message  # código 2: o Claude Code bloqueia o prompt e mostra a mensagem
    return 0, json.dumps({"systemMessage": message}, ensure_ascii=False) if message else "", ""


def proxy_missing(environ: dict[str, str] | None = None) -> str | None:
    """Se o agente não está apontado para o proxy do Véu, diz qual variável ajustar."""
    environ = os.environ if environ is None else environ
    for name in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
        if environ.get(name, "").startswith(PROXY_HOSTS):
            return None
    return ("Véu: o agente não está usando o proxy do Véu, então o prompt iria direto ao provedor. Rode 'veu servir' "
            "e defina ANTHROPIC_BASE_URL=http://localhost:8787 (Claude Code) ou OPENAI_BASE_URL=http://localhost:8787/v1.")


def check_prompt(data: dict, veu: Veu, *, mode: str = "avisar", block: frozenset[str] = SECRET_LABELS,
                 fmt: str = "claude", require_proxy: bool = False,
                 environ: dict[str, str] | None = None) -> tuple[int, str, str]:
    if require_proxy and (missing := proxy_missing(environ)):
        return _result(False, missing, fmt, "prompt")
    prompt = data.get("prompt") or data.get("user_prompt") or ""
    counts = Counter(entity.label for entity in veu.analyze(prompt))
    if not counts:
        return _result(True, "", fmt, "prompt")
    blocked = Counter({label: n for label, n in counts.items() if label in block})
    if blocked or mode == "bloquear":
        reason = blocked or counts
        return _result(False, f"Véu: o prompt não foi enviado porque contém {_names(reason)}. Tire esses dados "
                              "(ou troque por marcadores com 'veu anonimizar') e envie de novo.", fmt, "prompt")
    return _result(True, f"Véu: este prompt contém {_names(counts)}, que serão enviados ao provedor do modelo.",
                   fmt, "prompt")


def _file_path(data: dict) -> str | None:
    tool = data.get("tool_input") or {}
    return tool.get("file_path") or tool.get("path") or data.get("file_path")


def check_file(data: dict, veu: Veu, *, pii: str = "perguntar", block: frozenset[str] = SECRET_LABELS,
               fmt: str = "claude") -> tuple[int, str, str]:
    path = _file_path(data)
    content = data.get("content")
    if content is None and path:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
            return _result(True, "", fmt, "arquivo")
        from veu.documents import document_kind, read_document

        try:
            kind = document_kind(file)
            content = read_document(file, kind) if kind else file.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, ImportError, OSError, ValueError):
            return _result(True, "", fmt, "arquivo")  # binário ou ilegível: não é texto que vá para o modelo
    if not content:
        return _result(True, "", fmt, "arquivo")
    counts = Counter(entity.label for entity in veu.analyze(content))
    name = Path(path).name if path else "o arquivo"
    suggestion = (" Para ler o conteúdo com esses dados trocados por marcadores, use a ferramenta ler_protegido "
                  f"do Véu (MCP) ou rode: veu ler {path}" if path else "")
    blocked = Counter({label: n for label, n in counts.items() if label in block})
    if blocked:
        return _result(False, f"Véu: a leitura de {name} foi bloqueada porque ele contém {_names(blocked)}."
                              + suggestion, fmt, "arquivo")
    if counts and pii != "permitir":
        message = f"Véu: {name} contém {_names(counts)}." + suggestion
        if pii == "negar":
            return _result(False, message, fmt, "arquivo")
        return _result(True, message, fmt, "arquivo", ask=fmt == "claude")
    return _result(True, "", fmt, "arquivo")


def _scan(path: Path, veu: Veu, block: frozenset[str]) -> Counter:
    """Segredos (tipos em block) de um arquivo de texto pequeno; vazio se não der para ler."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return Counter()
        content = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return Counter()
    return Counter(entity.label for entity in veu.analyze(content) if entity.label in block)


def _command_files(command: str, cwd: Path) -> list[Path]:
    """Arquivos existentes citados num comando de terminal (cat .env, grep -r chave config/)."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    found = []
    for token in tokens:
        token = token.strip("'\"")
        if not token or token.startswith("-") or len(token) > 300 or any(c in token for c in "|;&<>$`*?"):
            continue
        path = Path(token).expanduser()
        path = path if path.is_absolute() else cwd / path
        try:
            if path.is_file():
                found.append(path)
        except OSError:
            continue
    return found


def _secret_files_under(folder: Path, glob: str | None, limit: int = 5000) -> list[Path]:
    """Arquivos com cara de segredo (.env, chaves, credentials.json) dentro de um diretório."""
    found, seen = [], 0
    for current, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            seen += 1
            if seen > limit:
                return found
            if SECRET_FILES.match(name) and (not glob or fnmatch.fnmatch(name, glob.lstrip("*/"))
                                             or fnmatch.fnmatch(name, glob)):
                found.append(Path(current) / name)
    return found


def check_command(data: dict, veu: Veu, *, block: frozenset[str] = SECRET_LABELS,
                  fmt: str = "claude") -> tuple[int, str, str]:
    """PreToolUse de Bash e Grep (e beforeShellExecution do Cursor)."""
    tool = data.get("tool_input") or {}
    cwd = Path(data.get("cwd") or os.getcwd())
    command = tool.get("command") or data.get("command")
    if data.get("tool_name") == "Grep" or (command is None and "pattern" in tool):
        if tool.get("output_mode") != "content":
            return _result(True, "", fmt, "comando")  # só nomes de arquivos ou contagens: nenhuma linha sai
        target = Path(tool.get("path") or cwd)
        target = target if target.is_absolute() else cwd / target
        files = [target] if target.is_file() else _secret_files_under(target, tool.get("glob"))
        risky = {path: counts for path in files if (counts := _scan(path, veu, block))}
        if risky:
            names = ", ".join(sorted({path.name for path in risky}))
            return _result(False, f"Véu: a busca mostraria linhas de {names}, que contém segredos. Restrinja a busca "
                                  "com glob (por exemplo, excluindo .env) ou use a ferramenta ler_protegido do Véu.",
                           fmt, "comando")
        return _result(True, "", fmt, "comando")
    if not isinstance(command, str) or not command.strip():
        return _result(True, "", fmt, "comando")
    if dumps_environment(command):
        return _result(False, "Véu: o comando mostraria as variáveis de ambiente, que costumam guardar chaves de API. "
                              "Para conferir se uma variável existe, use por exemplo: test -n \"$NOME\" && echo definida.",
                       fmt, "comando")
    if SECRET_VARIABLE.search(command) and re.search(r"\b(?:echo|printf|print|cat|Write-(?:Host|Output))\b",
                                                     command, re.IGNORECASE):
        return _result(False, "Véu: o comando mostraria o valor de uma variável com segredo. Use a variável no "
                              "programa sem imprimi-la.", fmt, "comando")
    for path in _command_files(command, cwd):
        counts = _scan(path, veu, block)
        if counts:
            return _result(False, f"Véu: o comando lê {path.name}, que contém {_names(counts)}. Para ver o conteúdo "
                                  f"com esses dados trocados por marcadores, use ler_protegido ou: veu ler {path}",
                           fmt, "comando")
    return _result(True, "", fmt, "comando")


def run(event: str, *, mode: str = "avisar", pii: str = "perguntar", block: frozenset[str] | None = None,
        fmt: str = "claude", veu: Veu | None = None, stdin=None, require_proxy: bool = False) -> int:
    raw = (stdin or sys.stdin).read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {"prompt": raw}
    veu = veu or Veu()
    block = SECRET_LABELS if block is None else block
    if event == "prompt":
        code, out, err = check_prompt(data, veu, mode=mode, block=block, fmt=fmt, require_proxy=require_proxy)
    elif event == "comando":
        code, out, err = check_command(data, veu, block=block, fmt=fmt)
    else:
        code, out, err = check_file(data, veu, pii=pii, block=block, fmt=fmt)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code
