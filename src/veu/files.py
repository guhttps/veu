"""Anonimização de arquivos de dados: texto, CSV, JSON e JSONL, com um único cofre para o arquivo inteiro.

O mesmo CPF recebe o mesmo marcador em todas as linhas, então análises e junções continuam funcionando.

    from veu.files import anonymize_file
    vault, counts = anonymize_file("clientes.csv", "clientes-anonimo.csv", force={"cpf": "CPF"})
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from veu.core import Veu
from veu.sessions import Session
from veu.vault import Vault

FORMATS = ("texto", "csv", "json", "jsonl")
_EXTENSIONS = {".csv": "csv", ".tsv": "csv", ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl"}


def detect_format(path: str | Path | None, explicit: str | None = None) -> str:
    if explicit:
        if explicit not in FORMATS:
            raise ValueError(f'Formato desconhecido: "{explicit}". Use um destes: {", ".join(FORMATS)}.')
        return explicit
    return _EXTENSIONS.get(Path(path).suffix.lower(), "texto") if path else "texto"


class DataAnonymizer:
    """Aplica uma sessão do Véu a campos de registros (dicts) e a células de tabelas.

    fields: só estes campos/colunas são analisados (padrão: todos os textos).
    force: {campo: TIPO} trata o campo inteiro como aquele dado, sem depender da detecção
    (útil para colunas como "cpf" sem pontuação ou "nome" com um só nome).
    """

    def __init__(self, session: Session, fields: Iterable[str] | None = None, force: Mapping[str, str] | None = None):
        self.session = session
        self.fields = set(fields) if fields else None
        self.force = {key: label.upper() for key, label in (force or {}).items()}

    @property
    def counts(self) -> Counter[str]:
        return self.session.counts

    def value(self, key: str | None, value: Any) -> Any:
        if key is not None and key in self.force:
            if value is None or (isinstance(value, str) and not value.strip()):
                return value
            text = str(value)
            self.session.counts[self.force[key]] += 1
            return self.session.anonymizer.replace_value(self.force[key], text, self.session.vault)
        if self.fields is not None and key not in self.fields:
            # Campos de fora da lista podem conter estruturas com campos da lista.
            return self.data(value) if isinstance(value, (dict, list)) else value
        if isinstance(value, str):
            return self.session.anonymize(value)
        if isinstance(value, (dict, list)):
            return self.data(value) if self.fields is not None else self.session.anonymize_data(value)
        return value

    def data(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self.value(key, item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.data(item) if isinstance(item, (dict, list)) else self.value(None, item) for item in value]
        return self.value(None, value)

    def restore_data(self, value: Any) -> Any:
        return self.session.restore_data(value)


def _sniff_dialect(sample: str, path: Path | None) -> type[csv.Dialect] | csv.Dialect:
    if path is not None and path.suffix.lower() == ".tsv":
        return csv.excel_tab
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def transform_csv(text: str, function, path: Path | None = None) -> str:
    """Aplica function(coluna, valor) a todas as células (o cabeçalho fica igual)."""
    dialect = _sniff_dialect(text[:20_000], path)
    rows = csv.reader(io.StringIO(text), dialect)
    output = io.StringIO()
    writer = csv.writer(output, dialect, lineterminator="\n")
    header = next(rows, None)
    if header is None:
        return ""
    writer.writerow(header)
    for row in rows:
        writer.writerow([function(header[i] if i < len(header) else None, cell) for i, cell in enumerate(row)])
    return output.getvalue()


def anonymize_text(text: str, file_format: str, data: DataAnonymizer, path: Path | None = None) -> str:
    if file_format == "csv":
        return transform_csv(text, data.value, path)
    if file_format == "json":
        return json.dumps(data.data(json.loads(text)), ensure_ascii=False, indent=2) + "\n"
    if file_format == "jsonl":
        lines = []
        for line in text.splitlines():
            lines.append(json.dumps(data.data(json.loads(line)), ensure_ascii=False) if line.strip() else line)
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return data.session.anonymize(text)


def restore_text(text: str, file_format: str, vault: Vault, path: Path | None = None) -> str:
    if file_format == "csv":
        return transform_csv(text, lambda _column, cell: vault.restore(cell), path)
    if file_format == "json":
        session = Session(Veu().anonymizer, vault)
        return json.dumps(session.restore_data(json.loads(text)), ensure_ascii=False, indent=2) + "\n"
    if file_format == "jsonl":
        session = Session(Veu().anonymizer, vault)
        lines = [json.dumps(session.restore_data(json.loads(line)), ensure_ascii=False) if line.strip() else line
                 for line in text.splitlines()]
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return vault.restore(text)


def anonymize_file(
    source: str | Path,
    destination: str | Path,
    *,
    veu: Veu | None = None,
    vault: Vault | None = None,
    file_format: str | None = None,
    fields: Iterable[str] | None = None,
    force: Mapping[str, str] | None = None,
) -> tuple[Vault, Counter[str]]:
    """Anonimiza um arquivo inteiro com um único cofre. Devolve o cofre e as contagens por tipo."""
    source, destination = Path(source), Path(destination)
    session = (veu or Veu()).session(vault)
    data = DataAnonymizer(session, fields, force)
    text = source.read_text(encoding="utf-8-sig")
    destination.write_text(anonymize_text(text, detect_format(source, file_format), data, source), encoding="utf-8")
    return session.vault, Counter(session.counts)


def restore_file(source: str | Path, destination: str | Path, vault: Vault, *, file_format: str | None = None) -> None:
    source, destination = Path(source), Path(destination)
    text = source.read_text(encoding="utf-8-sig")
    destination.write_text(restore_text(text, detect_format(source, file_format), vault, source), encoding="utf-8")
