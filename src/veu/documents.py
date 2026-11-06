"""Documentos do Office e PDF: leitura como texto e anonimização mantendo o formato.

    pip install "veu[documentos]"

- Word (.docx), Excel (.xlsx) e PowerPoint (.pptx) são anonimizados no próprio formato: a formatação, as fórmulas e
  o layout ficam iguais, só os dados mudam. A restauração devolve um documento com os dados reais.
- PDF é lido como texto (a saída anonimizada é texto, não PDF).
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from veu.vault import Vault

DOCUMENT_FORMATS = ("docx", "xlsx", "pptx", "pdf")
EXTENSIONS = {".docx": "docx", ".docm": "docx", ".xlsx": "xlsx", ".xlsm": "xlsx", ".pptx": "pptx", ".pdf": "pdf"}
WRITABLE = ("docx", "xlsx", "pptx")
MAX_ROWS = 20_000
INSTALL = 'Para ler documentos do Office e PDF, instale o suporte: pip install "veu[documentos]"'

# Trechos a trocar num parágrafo: (início, fim, texto novo).
Span = tuple[int, int, str]
Spans = Callable[[str], list[Span]]
CellFunction = Callable[[str | None, Any], Any]


def _module(name: str):
    import importlib

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(INSTALL) from exc


def document_kind(path: str | Path) -> str | None:
    return EXTENSIONS.get(Path(path).suffix.lower())


def _source(data: bytes | str | Path):
    return io.BytesIO(data) if isinstance(data, bytes) else str(data)


# Leitura como texto ------------------------------------------------------------------------------------------------

def _table_markdown(rows: list[list[str]]) -> str:
    rows = [[cell.replace("\n", " ").replace("|", "\\|").strip() for cell in row] for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


def _docx_blocks(document) -> Iterator[str]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            level = next((int(c) for c in style if c.isdigit()), 1)
            if style.lower().startswith(("heading", "título", "titulo", "title")):
                yield "#" * min(level, 6) + " " + text
            elif "list" in style.lower() or "lista" in style.lower():
                yield "- " + text
            else:
                yield text
        elif tag == "tbl":
            table = Table(child, document)
            yield _table_markdown([[cell.text for cell in row.cells] for row in table.rows])


def read_docx(data: bytes | str | Path) -> str:
    document = _module("docx").Document(_source(data))
    return "\n\n".join(block for block in _docx_blocks(document) if block)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def read_xlsx(data: bytes | str | Path) -> str:
    workbook = _module("openpyxl").load_workbook(_source(data), read_only=True, data_only=True)
    parts = []
    for sheet in workbook.worksheets:
        rows = []
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= MAX_ROWS:
                rows.append(["(linhas restantes omitidas)"])
                break
            rows.append([_cell_text(value) for value in row])
        table = _table_markdown(rows)
        if table:
            parts.append(f"## {sheet.title}\n\n{table}")
    workbook.close()
    return "\n\n".join(parts)


def read_pptx(data: bytes | str | Path) -> str:
    presentation = _module("pptx").Presentation(_source(data))
    parts = []
    for number, slide in enumerate(presentation.slides, 1):
        texts = []
        for shape in _pptx_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False):
                texts.append(_table_markdown([[cell.text for cell in row.cells] for row in shape.table.rows]))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            texts.append("Notas: " + slide.notes_slide.notes_text_frame.text.strip())
        parts.append(f"## Slide {number}\n\n" + "\n\n".join(texts))
    return "\n\n".join(parts)


def read_pdf(data: bytes | str | Path) -> str:
    reader = _module("pypdf").PdfReader(_source(data))
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"## Página {number}\n\n{text}")
    return "\n\n".join(pages)


READERS = {"docx": read_docx, "xlsx": read_xlsx, "pptx": read_pptx, "pdf": read_pdf}


def read_document(data: bytes | str | Path, kind: str) -> str:
    """Texto de um documento (Markdown simples, com tabelas e títulos)."""
    if kind not in READERS:
        raise ValueError(f'Formato de documento desconhecido: "{kind}". Use um destes: {", ".join(READERS)}.')
    return READERS[kind](data)


# Anonimização e restauração no próprio formato ---------------------------------------------------------------------

def apply_spans(runs: list, spans: Iterable[Span]) -> None:
    """Troca trechos de um parágrafo mantendo a formatação: cada substituto fica no trecho onde o dado começava."""
    chars: list[str] = []
    owners: list[int] = []
    for index, run in enumerate(runs):
        chars.extend(run.text)
        owners.extend([index] * len(run.text))
    changed = False
    for start, end, replacement in sorted(spans, key=lambda span: span[0], reverse=True):
        owner = owners[start] if start < len(owners) else (owners[-1] if owners else 0)
        chars[start:end] = list(replacement)
        owners[start:end] = [owner] * len(replacement)
        changed = True
    if not changed:
        return
    texts: list[list[str]] = [[] for _ in runs]
    for char, owner in zip(chars, owners, strict=True):
        texts[owner].append(char)
    for run, text in zip(runs, texts, strict=True):
        joined = "".join(text)
        if run.text != joined:
            run.text = joined


def _docx_runs(paragraph) -> list:
    """Trechos do parágrafo, inclusive os de dentro de links (um e-mail com link não pode escapar)."""
    runs = []
    for item in paragraph.iter_inner_content():
        runs.extend(item.runs if hasattr(item, "runs") else [item])
    return runs


def _rewrite(runs: list, spans: Spans) -> None:
    text = "".join(run.text for run in runs)
    if text.strip():
        apply_spans(runs, spans(text))


def _docx_paragraphs(container) -> Iterator:
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _docx_paragraphs(cell)


def _transform_docx(source: Path, destination: Path, spans: Spans, text: Callable[[str], str]) -> None:
    document = _module("docx").Document(str(source))
    containers = [document]
    for section in document.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            if not part.is_linked_to_previous:
                containers.append(part)
    seen: set[int] = set()
    for container in containers:
        for paragraph in _docx_paragraphs(container):
            if id(paragraph._p) in seen:
                continue  # células mescladas aparecem mais de uma vez
            seen.add(id(paragraph._p))
            _rewrite(_docx_runs(paragraph), spans)
    properties = document.core_properties
    for field in ("author", "last_modified_by", "title", "subject", "comments", "keywords"):
        value = getattr(properties, field)
        if value:
            setattr(properties, field, text(value))
    document.save(str(destination))


def _pptx_shapes(shapes) -> Iterator:
    for shape in shapes:
        if getattr(shape, "shape_type", None) == 6:  # grupo
            yield from _pptx_shapes(shape.shapes)
        else:
            yield shape


def _transform_pptx(source: Path, destination: Path, spans: Spans, text: Callable[[str], str]) -> None:
    presentation = _module("pptx").Presentation(str(source))
    frames = []
    for slide in presentation.slides:
        for shape in _pptx_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False):
                frames.append(shape.text_frame)
            if getattr(shape, "has_table", False):
                frames.extend(cell.text_frame for row in shape.table.rows for cell in row.cells)
        if slide.has_notes_slide:
            frames.append(slide.notes_slide.notes_text_frame)
    for frame in frames:
        for paragraph in frame.paragraphs:
            _rewrite(list(paragraph.runs), spans)
    properties = presentation.core_properties
    for field in ("author", "last_modified_by", "title", "subject", "comments", "keywords"):
        value = getattr(properties, field)
        if value:
            setattr(properties, field, text(value))
    presentation.save(str(destination))


def _transform_xlsx(source: Path, destination: Path, cell: CellFunction) -> None:
    workbook = _module("openpyxl").load_workbook(str(source))
    for sheet in workbook.worksheets:
        header: list[str | None] = []
        for index, row in enumerate(sheet.iter_rows()):
            if index == 0:
                header = [str(item.value) if item.value is not None else None for item in row]
                continue
            for column, item in enumerate(row):
                value = item.value
                if value is None or (isinstance(value, str) and value.startswith("=")):
                    continue  # fórmulas continuam fórmulas
                key = header[column] if column < len(header) else None
                new = cell(key, value)
                if new != value:
                    item.value = new
    workbook.save(str(destination))


def transform_document(source: str | Path, destination: str | Path, kind: str, *, spans: Spans,
                       text: Callable[[str], str], cell: CellFunction) -> None:
    source, destination = Path(source), Path(destination)
    if kind == "docx":
        _transform_docx(source, destination, spans, text)
    elif kind == "pptx":
        _transform_pptx(source, destination, spans, text)
    elif kind == "xlsx":
        _transform_xlsx(source, destination, cell)
    else:
        raise ValueError(f'Só dá para gerar documentos {", ".join(WRITABLE)} anonimizados; "{kind}" vira texto.')


def restore_spans(vault: Vault, text: str) -> list[Span]:
    """Os marcadores de um texto e o valor real de cada um (para restaurar documentos mantendo a formatação)."""
    spans = []
    for match in vault._compiled().finditer(text):
        original = vault._original_for(match)
        if original is not None:
            spans.append((match.start(), match.end(), original))
    return spans
