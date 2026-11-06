"""Ganchos (hooks) para agentes de código: Claude Code e Cursor.

    veu gancho prompt     # antes de enviar o prompt: bloqueia segredos, avisa sobre dados pessoais
    veu gancho arquivo    # antes de o agente ler um arquivo: bloqueia arquivos com segredos

O agente recebe o motivo e a sugestão de usar a ferramenta MCP ler_protegido, que lê o arquivo com os dados
trocados por marcadores. Nenhum valor real aparece nas mensagens: só os tipos e as quantidades.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from veu.core import Veu
from veu.entities import LABELS, SECRET_LABELS

MAX_FILE_BYTES = 2 * 1024 * 1024
FORMATS = ("claude", "cursor")


def _names(counts: Counter) -> str:
    return ", ".join(f"{count} {LABELS.get(label, label).split(' (')[0]}" for label, count in counts.most_common())


def _result(allow: bool, message: str, fmt: str, event: str, *, ask: bool = False) -> tuple[int, str, str]:
    """(código de saída, stdout, stderr) no formato de cada agente."""
    if fmt == "cursor":
        payload: dict = {"permission": "allow" if allow else "deny"} if event == "arquivo" else {"continue": allow}
        if message:
            payload.update(userMessage=message, agentMessage=message)
        return 0, json.dumps(payload, ensure_ascii=False), ""
    if event == "arquivo":
        if allow and not ask:
            return 0, json.dumps({"systemMessage": message}, ensure_ascii=False) if message else "", ""
        decision = "ask" if ask else "deny"
        return 0, json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": message,
        }}, ensure_ascii=False), ""
    if not allow:
        return 2, "", message  # código 2: o Claude Code bloqueia o prompt e mostra a mensagem
    return 0, json.dumps({"systemMessage": message}, ensure_ascii=False) if message else "", ""


def check_prompt(data: dict, veu: Veu, *, mode: str = "avisar", block: frozenset[str] = SECRET_LABELS,
                 fmt: str = "claude") -> tuple[int, str, str]:
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


def run(event: str, *, mode: str = "avisar", pii: str = "perguntar", block: frozenset[str] | None = None,
        fmt: str = "claude", veu: Veu | None = None, stdin=None) -> int:
    raw = (stdin or sys.stdin).read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {"prompt": raw}
    veu = veu or Veu()
    block = SECRET_LABELS if block is None else block
    if event == "prompt":
        code, out, err = check_prompt(data, veu, mode=mode, block=block, fmt=fmt)
    else:
        code, out, err = check_file(data, veu, pii=pii, block=block, fmt=fmt)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code
