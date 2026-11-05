"""Verificação de arquivos (pre-commit, CI, MCP) e relatórios em texto, anotações do GitHub, SARIF e JSON.

Os relatórios nunca trazem o valor completo: só a versão mascarada, para não repetir o dado no log.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from veu import __version__
from veu.anonymizer import mask_value
from veu.core import Veu
from veu.entities import LABELS

IGNORE_MARKERS = ("veu: ignorar", "veu:ignorar", "veu: ignore", "veu:ignore")
REPORT_FORMATS = ("texto", "github", "sarif", "json")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    label: str
    score: float
    masked: str


def check_text(text: str, path: str, veu: Veu) -> list[Finding]:
    lines = text.splitlines(keepends=True)
    starts, position = [], 0
    for line in lines:
        starts.append(position)
        position += len(line)
    findings = []
    for entity in veu.analyze(text):
        index = max(0, bisect.bisect_right(starts, entity.start) - 1)
        line = lines[index] if lines else ""
        if any(marker in line.lower() for marker in IGNORE_MARKERS):
            continue
        column = entity.start - (starts[index] if starts else 0) + 1
        findings.append(Finding(path, index + 1, column, entity.label, round(entity.score, 2),
                                mask_value(entity.label, entity.text)))
    return findings


def check_files(paths, veu: Veu, max_bytes: int = 20 * 1024 * 1024) -> tuple[list[Finding], list[str]]:
    """Verifica arquivos de texto (binários e arquivos grandes demais são ignorados). Devolve (achados, avisos)."""
    findings, warnings = [], []
    for path in paths:
        file = Path(path)
        try:
            if file.stat().st_size > max_bytes:
                warnings.append(f"{path}: ignorado (maior que {max_bytes // (1024 * 1024)} MB)")
                continue
            raw = file.read_bytes()
        except OSError as exc:
            warnings.append(f"{path}: não foi possível ler ({exc})")
            continue
        if b"\x00" in raw[:8192]:
            continue
        findings.extend(check_text(raw.decode("utf-8", errors="replace"), str(path), veu))
    return findings, warnings


def render(findings: list[Finding], report_format: str) -> str:
    if report_format == "json":
        return json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2) + "\n"
    if report_format == "github":
        lines = []
        for f in findings:
            message = f"{LABELS.get(f.label, f.label)} encontrado ({f.score:.0%}): {f.masked}"
            path = f.path.replace("\\", "/").replace(",", "%2C").replace(":", "%3A")
            lines.append(f"::error file={path},line={f.line},col={f.column},title=Véu {f.label}::{message}")
        return "\n".join(lines) + ("\n" if lines else "")
    if report_format == "sarif":
        return json.dumps(sarif(findings), ensure_ascii=False, indent=2) + "\n"
    return "".join(f"{f.path}:{f.line}:{f.column}: {f.label} ({f.score:.0%}) {f.masked}\n" for f in findings)


def sarif(findings: list[Finding]) -> dict:
    """Relatório SARIF 2.1.0, aceito pela aba Security do GitHub (code scanning) e por outras ferramentas."""
    used = sorted({f.label for f in findings})
    rules = [
        {
            "id": label,
            "name": label.title().replace("_", ""),
            "shortDescription": {"text": f"{LABELS.get(label, label)} em arquivo versionado"},
            "fullDescription": {"text": f"O Véu encontrou um dado pessoal do tipo {LABELS.get(label, label)}. "
                                        "Remova o dado real ou marque a linha com 'veu: ignorar' se for fictício."},
            "defaultConfiguration": {"level": "error"},
            "properties": {"tags": ["privacy", "lgpd", "pii"]},
        }
        for label in used
    ]
    results = [
        {
            "ruleId": f.label,
            "ruleIndex": used.index(f.label),
            "level": "error",
            "message": {"text": f"{LABELS.get(f.label, f.label)} encontrado: {f.masked}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.path.replace("\\", "/")},
                    "region": {"startLine": f.line, "startColumn": f.column},
                }
            }],
        }
        for f in findings
    ]
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "Véu", "version": __version__,
                                "informationUri": "https://github.com/guhttps/veu", "rules": rules}},
            "results": results,
        }],
    }
