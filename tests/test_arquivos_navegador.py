"""Arquivos protegidos pelo JavaScript da extensão (js/src/arquivos.ts) abrem no Word, no Excel e no PowerPoint.

O Python cria os documentos, o JavaScript protege e restaura, e as bibliotecas do Office abrem o resultado.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
openpyxl = pytest.importorskip("openpyxl")
pptx = pytest.importorskip("pptx")

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "js" / "dist" / "index.js"
SCRIPT = r"""
const fs = require("fs");
const { Veu, Vault, protectDocument, restoreDocument } = require(process.argv[1]);
(async () => {
  const [entrada, protegido, restaurado, tipo] = process.argv.slice(2);
  const veu = new Veu();
  const cofre = veu.newVault();
  const { bytes, counts } = await protectDocument(new Uint8Array(fs.readFileSync(entrada)), tipo, veu, cofre);
  fs.writeFileSync(protegido, bytes);
  fs.writeFileSync(restaurado, await restoreDocument(bytes, tipo, Vault.fromJSON(cofre.toJSON())));
  console.log(JSON.stringify(counts));
})();
"""

pytestmark = pytest.mark.skipif(not shutil.which("node") or not DIST.exists(), reason="precisa do Node e de js/dist")


def run_js(tmp_path: Path, source: Path, kind: str) -> tuple[Path, Path, dict]:
    protected, restored = tmp_path / f"protegido.{kind}", tmp_path / f"restaurado.{kind}"
    result = subprocess.run(["node", "-e", SCRIPT, str(DIST), str(source), str(protected), str(restored), kind],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    return protected, restored, json.loads(result.stdout)


def test_word(tmp_path):
    source = tmp_path / "contrato.docx"
    document = docx.Document()
    paragraph = document.add_paragraph("Contratante: ")
    paragraph.add_run("Maria").bold = True
    paragraph.add_run(" Souza, CPF 529.982.247-25.")
    document.core_properties.author = "Maria Souza"
    document.save(source)
    protected, restored, counts = run_js(tmp_path, source, "docx")
    opened = docx.Document(protected)
    text = "\n".join(p.text for p in opened.paragraphs)
    assert "Souza" not in text and "529.982" not in text and "[PESSOA_1]" in text
    assert opened.paragraphs[0].runs[1].bold  # o marcador fica no trecho em negrito, onde o nome começava
    assert opened.core_properties.author == ""
    assert counts == {"PESSOA": 1, "CPF": 1}
    assert docx.Document(restored).paragraphs[0].text == "Contratante: Maria Souza, CPF 529.982.247-25."


def test_excel(tmp_path):
    source = tmp_path / "clientes.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Nome", "CPF", "Pedidos"])
    sheet.append(["Joana Prado", 52998224725, 3])
    workbook.save(source)
    protected, restored, _ = run_js(tmp_path, source, "xlsx")
    values = [[cell.value for cell in row] for row in openpyxl.load_workbook(protected).active.iter_rows()]
    assert values[0] == ["Nome", "CPF", "Pedidos"]
    assert values[1] == ["[PESSOA_1]", "[CPF_1]", 3]
    again = [[cell.value for cell in row] for row in openpyxl.load_workbook(restored).active.iter_rows()]
    assert again[1] == ["Joana Prado", "52998224725", 3]  # o CPF volta como texto


def test_powerpoint(tmp_path):
    source = tmp_path / "apresentacao.pptx"
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Proposta para Carlos Mendes"
    slide.placeholders[1].text = "Contato: carlos.mendes@example.com"
    presentation.save(source)
    protected, restored, _ = run_js(tmp_path, source, "pptx")
    texts = [shape.text_frame.text for shape in pptx.Presentation(protected).slides[0].shapes if shape.has_text_frame]
    assert texts == ["Proposta para [PESSOA_1]", "Contato: [EMAIL_1]"]
    again = [shape.text_frame.text for shape in pptx.Presentation(restored).slides[0].shapes if shape.has_text_frame]
    assert again == ["Proposta para Carlos Mendes", "Contato: carlos.mendes@example.com"]
