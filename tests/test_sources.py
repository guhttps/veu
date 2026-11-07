"""Notion, Google, páginas web, documentos do Office e PDF, expansão de links no proxy e o comando veu ler."""

import asyncio
import json

import pytest

from veu import Veu
from veu import sources as src
from veu.cli import main
from veu.files import anonymize_file, restore_file
from veu.sources import Document, LinkExpander, SourceError, html_to_text, notion_id, read_source

CPF = "529.982.247-25"


# Notion -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.notion.so/empresa/Minha-Pagina-1f2e3d4c5b6a79788796a5b4c3d2e1f0",
    "https://www.notion.so/1f2e3d4c5b6a79788796a5b4c3d2e1f0?v=aaaabbbbccccddddeeeeffff00001111",
    "https://empresa.notion.site/Cafe-1f2e3d4c-5b6a-7978-8796-a5b4c3d2e1f0",
    "https://www.notion.so/empresa/Base-0123456789abcdef0123456789abcdef?p=1f2e3d4c5b6a79788796a5b4c3d2e1f0&pm=s",
])
def test_notion_id(url):
    assert notion_id(url) == "1f2e3d4c-5b6a-7978-8796-a5b4c3d2e1f0"


def rich(text):
    return [{"plain_text": text}]


def fake_notion(monkeypatch, *, page_found=True):
    calls = []

    def http(url, *, method="GET", headers=None, body=None, **_):
        calls.append((method, url, headers))
        assert headers["Authorization"] == "Bearer token-de-teste"
        page = "1f2e3d4c-5b6a-7978-8796-a5b4c3d2e1f0"
        if url.endswith(f"/pages/{page}"):
            if not page_found:
                raise SourceError("HTTP 404 ao ler https://api.notion.com/v1/pages")
            return json.dumps({"properties": {
                "Nome": {"type": "title", "title": rich("Atendimento")},
                "Responsável": {"type": "people", "people": [{"name": "Carla Mendes"}]},
            }}).encode(), "application/json"
        if f"/blocks/{page}/children" in url:
            return json.dumps({"results": [
                {"id": "b1", "type": "heading_2", "heading_2": {"rich_text": rich("Cliente")}},
                {"id": "b2", "type": "paragraph", "paragraph": {"rich_text": rich(f"Maria Souza, CPF {CPF}")}},
                {"id": "b3", "type": "to_do", "to_do": {"rich_text": rich("Ligar de volta"), "checked": True},
                 "has_children": True},
                {"id": "b4", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rich("um")}},
                {"id": "b5", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rich("dois")}},
            ], "has_more": False}).encode(), "application/json"
        if "/blocks/b3/children" in url:
            return json.dumps({"results": [
                {"id": "c1", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich("tel (11) 98765-4321")}},
            ], "has_more": False}).encode(), "application/json"
        if url.endswith(f"/databases/{page}"):
            return json.dumps({"title": rich("Clientes"), "properties": {"Nome": {}, "CPF": {}}}).encode(), ""
        if url.endswith(f"/databases/{page}/query"):
            return json.dumps({"results": [{"properties": {
                "Nome": {"type": "title", "title": rich("João Pereira")},
                "CPF": {"type": "rich_text", "rich_text": rich(CPF)},
            }}], "has_more": False}).encode(), ""
        raise AssertionError(url)

    monkeypatch.setattr(src, "http", http)
    monkeypatch.setenv("NOTION_TOKEN", "token-de-teste")
    return calls


def test_notion_page_to_markdown(monkeypatch):
    calls = fake_notion(monkeypatch)
    document = read_source("https://www.notion.so/empresa/Atendimento-1f2e3d4c5b6a79788796a5b4c3d2e1f0")
    assert document.kind == "notion" and document.title == "Atendimento"
    assert "## Cliente" in document.text and f"Maria Souza, CPF {CPF}" in document.text
    assert "- [x] Ligar de volta" in document.text and "  - tel (11) 98765-4321" in document.text
    assert "1. um" in document.text and "2. dois" in document.text
    assert "**Responsável:** Carla Mendes" in document.text
    assert all(headers["Notion-Version"] for _, _, headers in calls)
    protected = Veu().anonymize(document.text).text
    assert CPF not in protected and "Maria Souza" not in protected and "98765-4321" not in protected


def test_notion_database_as_table(monkeypatch):
    fake_notion(monkeypatch, page_found=False)
    document = read_source("https://www.notion.so/1f2e3d4c5b6a79788796a5b4c3d2e1f0?v=1")
    assert document.text.startswith("# Clientes")
    assert f"| João Pereira | {CPF} |" in document.text


def test_notion_without_token_explains_how(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    with pytest.raises(SourceError, match="NOTION_TOKEN"):
        read_source("https://www.notion.so/Pagina-1f2e3d4c5b6a79788796a5b4c3d2e1f0")


# Google -----------------------------------------------------------------------------------------------------------

def test_google_sheet_public_export(monkeypatch):
    seen = []

    def http(url, headers=None, **_):
        seen.append((url, headers))
        return f"nome,cpf\nMaria Souza,{CPF}\n".encode(), "text/csv"

    monkeypatch.setattr(src, "http", http)
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    document = read_source("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=42")
    assert seen[0][0].endswith("/export?format=csv&gid=42")
    assert document.kind == "google-sheets" and f"| Maria Souza | {CPF} |" in document.text


def test_google_private_doc_with_token_and_without(monkeypatch):
    def private(url, headers=None, **_):
        if headers and headers.get("Authorization") == "Bearer abc":
            assert "googleapis.com/drive/v3/files/" in url and "text%2Fplain" in url
            return b"Contrato de Maria Souza", "text/plain"
        return b"<html>login</html>", "text/html"

    monkeypatch.setattr(src, "http", private)
    url = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    with pytest.raises(SourceError, match="Qualquer pessoa com o link"):
        read_source(url)
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "abc")
    assert read_source(url).text == "Contrato de Maria Souza"


# Web --------------------------------------------------------------------------------------------------------------

def test_html_to_text_skips_scripts():
    title, text = html_to_text("<html><head><title>Ficha</title><script>var x='Ana Lima'</script></head>"
                               "<body><h1>Cliente</h1><p>Maria&nbsp;Souza</p><ul><li>CPF 1</li></ul></body></html>")
    assert title == "Ficha" and "Ana Lima" not in text
    assert "# Cliente" in text and "Maria Souza" in text and "- CPF 1" in text


# Documentos -------------------------------------------------------------------------------------------------------

def test_docx_keeps_formatting_and_round_trips(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Ficha do cliente", 1)
    paragraph = document.add_paragraph("Cliente ")
    paragraph.add_run("Maria").bold = True
    paragraph.add_run(f" Souza, CPF {CPF}.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Telefone", "(11) 98765-4321"
    table.cell(1, 0).text, table.cell(1, 1).text = "E-mail", "maria.souza@example.com"
    document.sections[0].header.paragraphs[0].text = "Atendente: Carla Mendes"
    document.core_properties.author = "Carla Mendes"
    source, protected, back = tmp_path / "ficha.docx", tmp_path / "protegida.docx", tmp_path / "volta.docx"
    document.save(source)

    vault, counts = anonymize_file(source, protected)
    result = docx.Document(protected)
    body = "\n".join(p.text for p in result.paragraphs)
    cells = [cell.text for row in result.tables[0].rows for cell in row.cells]
    assert "Maria" not in body and CPF not in body and "[PESSOA_1]" in body and "[CPF_1]" in body
    assert "(11) 98765-4321" not in cells and "maria.souza@example.com" not in cells
    assert "Carla" not in result.sections[0].header.paragraphs[0].text
    assert result.core_properties.author != "Carla Mendes"
    assert result.paragraphs[1].runs[1].bold  # o nome ficou no trecho em negrito
    assert counts["CPF"] == 1 and counts["TELEFONE"] == 1

    restore_file(protected, back, vault)
    restored = docx.Document(back)
    assert restored.paragraphs[1].text == f"Cliente Maria Souza, CPF {CPF}."
    assert restored.tables[0].cell(0, 1).text == "(11) 98765-4321"
    assert restored.sections[0].header.paragraphs[0].text == "Atendente: Carla Mendes"


def test_xlsx_cells_formulas_and_forced_columns(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["nome", "cpf", "observacao", "total"])
    sheet.append(["Maria Souza", 52998224725, "ligar no (11) 98765-4321", "=1+1"])
    source, protected, back = tmp_path / "clientes.xlsx", tmp_path / "protegida.xlsx", tmp_path / "volta.xlsx"
    workbook.save(source)

    vault, counts = anonymize_file(source, protected, force={"cpf": "CPF", "nome": "PESSOA"})
    row = [cell.value for cell in openpyxl.load_workbook(protected).active[2]]
    assert row == ["[PESSOA_1]", "[CPF_1]", "ligar no [TELEFONE_1]", "=1+1"]
    assert counts == {"PESSOA": 1, "CPF": 1, "TELEFONE": 1}
    restore_file(protected, back, vault)
    restored = [cell.value for cell in openpyxl.load_workbook(back).active[2]]
    assert restored == ["Maria Souza", "52998224725", "ligar no (11) 98765-4321", "=1+1"]


def test_pptx_round_trip(tmp_path):
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches

    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Caso de Maria Souza"
    slide.placeholders[1].text = f"CPF {CPF}"
    table = slide.shapes.add_table(1, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Contato", "(11) 98765-4321"
    source, protected, back = tmp_path / "caso.pptx", tmp_path / "protegido.pptx", tmp_path / "volta.pptx"
    presentation.save(source)

    vault, _ = anonymize_file(source, protected)
    from veu.documents import read_pptx

    text = read_pptx(protected)
    assert "Maria Souza" not in text and CPF not in text and "98765-4321" not in text
    restore_file(protected, back, vault)
    assert "Caso de Maria Souza" in read_pptx(back) and CPF in read_pptx(back)


def minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(output)


def test_pdf_becomes_protected_text(tmp_path):
    pytest.importorskip("pypdf")
    source = tmp_path / "laudo.pdf"
    source.write_bytes(minimal_pdf(f"Paciente Maria Souza CPF {CPF}"))
    assert f"Maria Souza CPF {CPF}" in read_source(str(source)).text
    with pytest.raises(ValueError, match="texto"):
        anonymize_file(source, tmp_path / "saida.pdf")
    anonymize_file(source, tmp_path / "laudo.txt")
    text = (tmp_path / "laudo.txt").read_text(encoding="utf-8")
    assert "[PESSOA_1]" in text and "[CPF_1]" in text and CPF not in text


# Proxy e MCP ------------------------------------------------------------------------------------------------------

def test_link_expander_only_allowed_domains_and_cache():
    reads = []

    def reader(url):
        reads.append(url)
        return Document(url, "", f"Responsável: Maria Souza, CPF {CPF}", "notion")

    expander = LinkExpander(reader=reader)
    url = "https://www.notion.so/Caso-1f2e3d4c5b6a79788796a5b4c3d2e1f0"
    text = f"Resuma {url}. Ignore http://169.254.169.254/latest e https://exemplo.com/x"
    expanded = expander.expand(text)
    assert f"[Conteúdo de {url}]" in expanded and CPF in expanded
    assert reads == [url]
    expander.expand(text)
    assert reads == [url]  # do cache
    assert not expander.allowed("http://www.notion.so/x") and not expander.allowed("https://notion.so.mal.example/x")


def test_proxy_expands_links_before_masking(monkeypatch):
    from veu.config import Config
    from veu.gateway.adapters import detect_adapter
    from veu.gateway.pipeline import Gateway

    monkeypatch.setattr(src, "read_source",
                        lambda url, **_: Document(url, "", f"Cliente Maria Souza, CPF {CPF}", "notion"))
    gateway = Gateway(Veu(Config(expand_links=True)))
    gateway.expander.reader = src.read_source
    body = json.dumps({"model": "m", "messages": [
        {"role": "user", "content": "Resuma https://www.notion.so/Caso-1f2e3d4c5b6a79788796a5b4c3d2e1f0"},
        {"role": "assistant", "tool_calls": [{"function": {"arguments": '{"url": "https://www.notion.so/x-1f2e3d4c5b6a79788796a5b4c3d2e1f0"}'}}]},
    ]}).encode()
    prepared = gateway.prepare(detect_adapter("POST", "/v1/chat/completions"), body)
    sent = json.loads(prepared.body)
    user = sent["messages"][-2]["content"]
    assert "[Conteúdo de" in user and "[CPF_1]" in user and CPF not in prepared.body.decode()
    assert "Conteúdo de" not in sent["messages"][-1]["tool_calls"][0]["function"]["arguments"]


def test_toml_options(tmp_path):
    from veu.config import load_config

    path = tmp_path / "veu.toml"
    path.write_text('[servidor]\nexpandir_links = true\ndominios_expandidos = ["notion.so", "wiki.empresa.example"]\n',
                    encoding="utf-8")
    config = load_config(str(path))
    assert config.expand_links and config.expand_domains == ("notion.so", "wiki.empresa.example")


def test_mcp_ler_protegido(tmp_path):
    pytest.importorskip("mcp")
    docx = pytest.importorskip("docx")
    from mcp.client import Client

    from veu.integrations.mcp import build_server

    path = tmp_path / "ficha.docx"
    document = docx.Document()
    document.add_paragraph(f"Cliente Maria Souza, CPF {CPF}")
    document.save(path)

    async def run():
        async with Client(build_server()) as client:
            read = await client.call_tool("ler_protegido", {"fonte": str(path)})
            back = await client.call_tool("restaurar_texto", {"texto": "Olá [PESSOA_1]",
                                                              "sessao": read.structured_content["sessao"]})
            check = await client.call_tool("verificar_arquivo", {"caminho": str(path)})
            missing = await client.call_tool("ler_protegido", {"fonte": str(tmp_path / "nao.docx")})
            return read, back, check, missing

    read, back, check, missing = asyncio.run(run())
    assert read.structured_content["texto"] == "Cliente [PESSOA_1], CPF [CPF_1]"
    assert read.structured_content["tipo"] == "docx" and read.structured_content["escondidos"] == {"PESSOA": 1, "CPF": 1}
    assert back.content[0].text == "Olá Maria Souza"
    assert check.structured_content["por_entidade"] == {"PESSOA": 1, "CPF": 1}
    assert missing.is_error and "não encontrado" in missing.content[0].text


# CLI --------------------------------------------------------------------------------------------------------------

def test_cli_ler_and_office_files(tmp_path, capsys, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.append(["nome", "cpf"])
    workbook.active.append(["Maria Souza", CPF])
    source = tmp_path / "planilha.xlsx"
    workbook.save(source)

    assert main(["ler", str(source), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["tipo"] == "xlsx" and "| [PESSOA_1] | [CPF_1] |" in output["texto"]

    cofre = tmp_path / "cofre.json"
    assert main(["anonimizar", str(source), "-o", str(tmp_path / "p.xlsx"), "--cofre", str(cofre)]) == 0
    assert openpyxl.load_workbook(tmp_path / "p.xlsx").active["B2"].value == "[CPF_1]"
    assert main(["restaurar", str(tmp_path / "p.xlsx"), "--cofre", str(cofre), "-o", str(tmp_path / "v.xlsx")]) == 0
    assert openpyxl.load_workbook(tmp_path / "v.xlsx").active["B2"].value == CPF
    assert main(["anonimizar", str(source)]) == 2  # documento precisa de -o
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    assert main(["ler", "https://www.notion.so/Pagina-1f2e3d4c5b6a79788796a5b4c3d2e1f0"]) == 2
    assert "NOTION_TOKEN" in capsys.readouterr().err


def fake_notion_people(monkeypatch):
    page = "1f2e3d4c-5b6a-7978-8796-a5b4c3d2e1f0"

    def http(url, *, method="GET", headers=None, body=None, **_):
        if url.endswith(f"/pages/{page}"):
            return json.dumps({"properties": {
                "Nome": {"type": "title", "title": rich("rafael. Moura")},
                "Pessoa": {"type": "people", "people": [{"name": "rafael. Moura", "person": {"email": "rafa@empresa.example"}}]},
                "Criado por": {"type": "created_by", "created_by": {"name": "bia. Lopes"}},
            }}).encode(), "application/json"
        if f"/blocks/{page}/children" in url:
            return json.dumps({"results": [{"id": "b1", "type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "plain_text": "Falar com "},
                {"type": "mention", "plain_text": "@tom. Reis", "mention": {"type": "user", "user": {"name": "tom. Reis"}}},
                {"type": "text", "plain_text": " sobre o contrato de rafael. Moura."},
            ]}}], "has_more": False}).encode(), "application/json"
        raise AssertionError(url)

    monkeypatch.setattr(src, "http", http)
    monkeypatch.setenv("NOTION_TOKEN", "token-de-teste")


def test_notion_people_are_hidden_even_when_detection_misses(monkeypatch):
    from veu.sources import protect_document

    fake_notion_people(monkeypatch)
    veu = Veu()
    assert veu.analyze("rafael. Moura") == []  # a detecção sozinha não pega este formato
    document = read_source("https://app.notion.com/p/Pagina-1f2e3d4c5b6a79788796a5b4c3d2e1f0")
    assert document.known == {"rafael. Moura": "PESSOA", "rafa@empresa.example": "EMAIL", "bia. Lopes": "PESSOA",
                              "tom. Reis": "PESSOA"}
    title, text, counts = protect_document(document, veu.anonymizer, veu.new_vault())
    assert title == "[PESSOA_1]"
    for name in ("rafael", "Moura", "bia", "Lopes", "tom. Reis"):
        assert name not in text
    assert "@[PESSOA_3]" in text and counts["PESSOA"] >= 4


def test_cli_ler_and_proxy_hide_notion_people(monkeypatch, capsys):
    from veu.config import Config
    from veu.gateway.adapters import detect_adapter
    from veu.gateway.pipeline import Gateway

    fake_notion_people(monkeypatch)
    url = "https://app.notion.com/p/Pagina-1f2e3d4c5b6a79788796a5b4c3d2e1f0"
    assert main(["ler", url, "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert "Moura" not in json.dumps(output) and output["escondidos"]["PESSOA"] >= 3

    gateway = Gateway(Veu(Config(expand_links=True)))
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": f"Resuma {url}"}]}).encode()
    prepared = gateway.prepare(detect_adapter("POST", "/v1/chat/completions"), body)
    sent = prepared.body.decode()
    assert "[Conteúdo de" in sent and "Moura" not in sent and "Reis" not in sent
