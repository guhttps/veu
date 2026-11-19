"""Arquivos maliciosos: XXE, billion laughs, zip bomb e PDF bomb não leem o disco nem derrubam o processo."""

import io
import zipfile
import zlib

import httpx
import pytest

pytest.importorskip("docx")
pytest.importorskip("openpyxl")
pytest.importorskip("pypdf")

from test_server import Upstream, call  # noqa: E402

from veu.config import Config  # noqa: E402
from veu.documents import read_document  # noqa: E402
from veu.server import create_app  # noqa: E402
from veu.server.panel import PanelController  # noqa: E402

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _swap(original: bytes, name: str, content: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(original))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, content if item.filename == name else source.read(item))
    return output.getvalue()


def docx_with(body: str, doctype: str = "") -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    Document().save(buffer)
    xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>{doctype}<w:document {W}><w:body><w:p><w:r>'
           f"<w:t>{body}</w:t></w:r></w:p></w:body></w:document>")
    return _swap(buffer.getvalue(), "word/document.xml", xml.encode())


def xlsx_with(cell: str, doctype: str = "") -> bytes:
    """Planilha cuja célula A1 tem o texto dado (string embutida na própria planilha)."""
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active["A1"] = "texto"
    buffer = io.BytesIO()
    workbook.save(buffer)
    sheet = (f'<?xml version="1.0"?>{doctype}<worksheet {S}><sheetData><row r="1"><c r="A1" t="inlineStr"><is>'
             f"<t>{cell}</t></is></c></row></sheetData></worksheet>")
    return _swap(buffer.getvalue(), "xl/worksheets/sheet1.xml", sheet.encode())


def read_or_refuse(data: bytes, kind: str) -> str:
    try:
        return read_document(data, kind)
    except Exception:  # noqa: BLE001 (recusar também protege)
        return ""


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / "segredo.txt"
    path.write_text("SEGREDO-DO-DISCO", encoding="utf-8")
    return path.resolve().as_uri()


def test_xxe_never_reads_local_files(secret_file):
    doctype = f'<!DOCTYPE d [<!ENTITY x SYSTEM "{secret_file}">]>'
    assert "SEGREDO-DO-DISCO" not in read_document(docx_with("&x;", doctype), "docx")
    assert read_document(xlsx_with("injetado"), "xlsx").count("injetado") == 1  # a injeção funciona
    xxe = xlsx_with("&x;", f'<!DOCTYPE s [<!ENTITY x SYSTEM "{secret_file}">]>')
    assert "SEGREDO-DO-DISCO" not in read_or_refuse(xxe, "xlsx")


def test_billion_laughs_does_not_expand():
    laughs = '<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">' + "".join(
        f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(8)) + "]>"
    with pytest.raises(Exception):  # noqa: B017 (o lxml recusa a amplificação)
        read_document(docx_with("&i;", laughs), "docx")
    assert len(read_or_refuse(xlsx_with("&i;", laughs), "xlsx")) < 1000


@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_zip_bomb_is_refused_before_opening(kind):
    """Um .docx de 300 KB guardava 300 MB de XML e passava de 600 MB de memória ao ser lido."""
    bomb = docx_with("a" * 20_000_000) if kind == "docx" else xlsx_with("a" * 20_000_000)
    assert len(bomb) < 200_000
    with pytest.raises(ValueError, match="zip bomb"):
        read_document(bomb, kind)


def pdf_bomb() -> bytes:
    # 320 MB num fluxo: passa do limite do pypdf (75 MB por fluxo), que vira um erro claro.
    content = zlib.compress(b"BT /F1 12 Tf 10 10 Td (a) Tj ET\n" * 10_000_000, 9)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content) + content + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    size = len(objects) + 1
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % size + b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    return pdf + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)


def test_pdf_bomb_is_a_clear_error():
    with pytest.raises(ValueError, match="PDF"):
        read_document(pdf_bomb(), "pdf")


def test_panel_answers_400_for_a_bomb(tmp_path):
    controller = PanelController(tmp_path / "veu.toml", key="chave-do-painel-de-teste-com-32-letras")
    app = create_app(Config(), upstream_transport=httpx.MockTransport(Upstream()), panel=controller)
    headers = {"x-veu-painel": controller.key}
    for name, content in (("bomba.docx", docx_with("a" * 20_000_000)), ("bomba.pdf", pdf_bomb())):
        response = call(app, "POST", f"/veu/painel/arquivos/proteger?nome={name}", content=content, headers=headers)
        assert response.status_code == 400, name
