// Word, Excel e PowerPoint protegidos e restaurados no próprio formato, sem dependências.
import assert from "node:assert/strict";
import { test } from "node:test";
import { Veu, protectDocument, readZip, restoreDocument, writeZip } from "../src/index.ts";

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
const enc = (text: string) => new TextEncoder().encode(text);
const dec = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

function docx(body: string): Promise<Uint8Array> {
  return writeZip(new Map([
    ["[Content_Types].xml", enc('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')],
    ["word/document.xml", enc(`<?xml version="1.0" encoding="UTF-8"?><w:document ${W}><w:body>${body}</w:body></w:document>`)],
    ["docProps/core.xml", enc("<cp:coreProperties><dc:creator>Maria Souza</dc:creator><cp:lastModifiedBy>Maria Souza</cp:lastModifiedBy></cp:coreProperties>")],
  ]));
}

test("zip gravado e lido de volta, com o CRC certo", async () => {
  const files = new Map([["a.txt", enc("olá ".repeat(1000))], ["pasta/b.xml", enc("<x/>")]]);
  const again = await readZip(await writeZip(files));
  assert.deepEqual([...again.keys()], ["a.txt", "pasta/b.xml"]);
  assert.equal(dec(again.get("a.txt")!), "olá ".repeat(1000));
});

test("Word: nome dividido pela formatação, CPF, autor nos metadados e a volta", async () => {
  const body = '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Cliente Ma</w:t></w:r><w:r><w:t>ria Souza</w:t></w:r>'
    + '<w:r><w:t xml:space="preserve">, CPF 529.982.247-25 &amp; telefone </w:t></w:r><w:r><w:tab/><w:t>(11) 98765-4321</w:t></w:r></w:p>';
  const original = await docx(body);
  const veu = new Veu();
  const vault = veu.newVault();
  const { bytes, counts } = await protectDocument(original, "docx", veu, vault);
  const files = await readZip(bytes);
  const xml = dec(files.get("word/document.xml")!);
  assert.ok(!xml.includes("Souza") && !xml.includes("529.982") && !xml.includes("98765"), xml);
  assert.match(xml, /\[PESSOA_1\]/);
  assert.equal((xml.match(/<w:r>/g) || []).length, 4); // os trechos (e a formatação) continuam
  assert.match(xml, /<w:b\/>/);
  assert.match(xml, /&amp; telefone/);
  assert.deepEqual(counts, { PESSOA: 1, CPF: 1, TELEFONE: 1 });
  assert.equal(dec(files.get("docProps/core.xml")!), "<cp:coreProperties><dc:creator></dc:creator><cp:lastModifiedBy></cp:lastModifiedBy></cp:coreProperties>");

  const restored = dec((await readZip(await restoreDocument(bytes, "docx", vault))).get("word/document.xml")!);
  assert.match(restored, /Maria Souza/);
  assert.match(restored, /529\.982\.247-25/);
  assert.match(restored, /\(11\) 98765-4321/);
});

test("Excel: textos compartilhados, texto na célula e CPF guardado como número", async () => {
  const sheet = '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>52998224725</v></c>'
    + '<c r="C1"><v>1234</v></c><c r="D1" t="inlineStr"><is><t>e-mail ana.lima@example.com</t></is></c></row></sheetData></worksheet>';
  const original = await writeZip(new Map([
    ["xl/sharedStrings.xml", enc('<sst><si><t>Cliente Joana Prado</t></si></sst>')],
    ["xl/worksheets/sheet1.xml", enc(sheet)],
  ]));
  const veu = new Veu();
  const vault = veu.newVault();
  const { bytes } = await protectDocument(original, "xlsx", veu, vault);
  const files = await readZip(bytes);
  assert.equal(dec(files.get("xl/sharedStrings.xml")!), "<sst><si><t>Cliente [PESSOA_1]</t></si></sst>");
  const xml = dec(files.get("xl/worksheets/sheet1.xml")!);
  assert.match(xml, /<c r="B1" t="inlineStr"><is><t>\[CPF_1\]<\/t><\/is><\/c>/);
  assert.match(xml, /<c r="C1"><v>1234<\/v><\/c>/); // número comum fica
  assert.match(xml, /e-mail \[EMAIL_1\]/);
  const restored = dec((await readZip(await restoreDocument(bytes, "xlsx", vault))).get("xl/worksheets/sheet1.xml")!);
  assert.match(restored, /52998224725/);
});

test("PowerPoint: slides e anotações", async () => {
  const slide = '<p:sld><p:txBody><a:p><a:r><a:t>Apresentação para Carlos Mendes</a:t></a:r></a:p></p:txBody></p:sld>';
  const original = await writeZip(new Map([
    ["ppt/slides/slide1.xml", enc(slide)], ["ppt/notesSlides/notesSlide1.xml", enc(slide.replace("Carlos", "Carlos"))],
    ["ppt/theme/theme1.xml", enc("<a:theme>Carlos Mendes</a:theme>")],
  ]));
  const veu = new Veu();
  const { bytes } = await protectDocument(original, "pptx", veu, veu.newVault());
  const files = await readZip(bytes);
  assert.match(dec(files.get("ppt/slides/slide1.xml")!), /para \[PESSOA_1\]/);
  assert.match(dec(files.get("ppt/notesSlides/notesSlide1.xml")!), /para \[PESSOA_1\]/);
  assert.equal(dec(files.get("ppt/theme/theme1.xml")!), "<a:theme>Carlos Mendes</a:theme>"); // fora do texto do slide
});

test("zip bomb é recusada antes de descompactar", async () => {
  const bomb = await writeZip(new Map([["word/document.xml", enc("a".repeat(20_000_000))]]));
  assert.ok(bomb.length < 200_000);
  await assert.rejects(readZip(bomb), /zip bomb/);
});

test("arquivo que não é do Office dá um erro claro", async () => {
  await assert.rejects(readZip(enc("isto não é um zip")), /Office/);
});
