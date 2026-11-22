// Imagens: palavras lidas num print (com as caixas) viram tarjas sobre os dados, sem depender do leitor de imagem.
import assert from "node:assert/strict";
import { test } from "node:test";
import { Veu, imageRedactions, wordsFromTesseract } from "../src/index.ts";
import type { OcrWord } from "../src/index.ts";

const veu = new Veu();
const analyze = (text: string) => veu.analyze(text);

/** Linhas de texto viram palavras com caixas de 10 px por letra, uma linha a cada 30 px. */
function words(...lines: string[]): OcrWord[] {
  const result: OcrWord[] = [];
  lines.forEach((line, row) => {
    let x = 0;
    for (const text of line.split(" ")) {
      result.push({ text, bbox: { x0: x, y0: row * 30, x1: x + text.length * 10, y1: row * 30 + 20 }, line: row });
      x += (text.length + 1) * 10;
    }
  });
  return result;
}

test("cada dado do print vira uma tarja sobre as palavras onde ele está", () => {
  const { boxes, counts, text } = imageRedactions(words(
    "Nome: Carlos Eduardo Lima",
    "CPF: 390.533.447-05 RG: 12.345.678-9",
    "Placa do veículo: BRA2E19",
  ), analyze, 0);
  assert.equal(text, "Nome: Carlos Eduardo Lima\nCPF: 390.533.447-05 RG: 12.345.678-9\nPlaca do veículo: BRA2E19");
  assert.deepEqual(counts, { PESSOA: 1, CPF: 1, RG: 1, PLACA: 1 });
  // O nome ocupa as três últimas palavras da primeira linha: uma tarja só, do "Carlos" ao "Lima".
  assert.deepEqual(boxes.find((box) => box.y0 === 0), { x0: 60, y0: 0, x1: 250, y1: 20 });
  assert.equal(boxes.length, 4);
});

test("o @ que o leitor errou não deixa o e-mail escapar", () => {
  // Numa palavra só ("&M" no lugar do "@") e em duas palavras ("ribeiro&" + "exemplo.com.br").
  const uma = imageRedactions(words("e-mail: beatriz.nogueira&Mexemplo.com.br"), analyze, 0);
  assert.deepEqual(uma.counts, { EMAIL: 1 });
  assert.match(uma.text, /beatriz\.nogueira@exemplo\.com\.br/);
  const duas = imageRedactions(words("Chave Pix helena.ribeiro& exemplo.com.br"), analyze, 0);
  assert.equal(duas.counts.EMAIL, 1);
  assert.deepEqual(duas.boxes, [{ x0: 100, y0: 0, x1: 400, y1: 20 }]); // cobre as duas palavras
});

test("um dado quebrado em duas linhas ganha uma tarja em cada linha", () => {
  const { boxes } = imageRedactions(words("Endereço: Rua das Palmeiras,", "455, apto 12"), analyze, 0);
  assert.ok(boxes.some((box) => box.y0 === 0));
  assert.ok(boxes.some((box) => box.y0 === 30));
});

test("print sem dados não ganha tarja", () => {
  const { boxes, counts } = imageRedactions(words("Reunião às 10h sobre o relatório", "Pauta: metas do trimestre"), analyze);
  assert.deepEqual(boxes, []);
  assert.deepEqual(counts, {});
});

test("o resultado do Tesseract vira palavras em ordem, uma linha por linha lida", () => {
  const bbox = { x0: 0, y0: 0, x1: 1, y1: 1 };
  const lidas = wordsFromTesseract([{ paragraphs: [
    { lines: [{ words: [{ text: "Ana", bbox }, { text: " ", bbox }, { text: "Lima", bbox }] }, { words: [{ text: "CPF", bbox }] }] },
  ] }]);
  assert.deepEqual(lidas.map((w) => [w.text, w.line]), [["Ana", 0], ["Lima", 0], ["CPF", 1]]);
  assert.deepEqual(wordsFromTesseract(null), []);
});
