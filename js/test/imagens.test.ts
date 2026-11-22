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

// Códigos de barras -------------------------------------------------------------------------------------------------
import { barcodeBoxes } from "../src/index.ts";

function blankImage(width: number, height: number) {
  return { width, height, data: new Uint8ClampedArray(width * height * 4).fill(255) };
}
function paint(image: ReturnType<typeof blankImage>, x0: number, y0: number, x1: number, y1: number, value = 0) {
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) image.data.fill(value, (y * image.width + x) * 4, (y * image.width + x) * 4 + 3);
}
// ITF (intercalado 2 de 5, o do boleto): N = estreito (1 módulo), W = largo (3 módulos).
const ITF = ["NNWWN", "WNNNW", "NWNNW", "WWNNN", "NNWNW", "WNWNN", "NWWNN", "NNNWW", "WNNWN", "NWNWN"];
/** Desenha um código ITF; devolve a largura. */
function itf(image: ReturnType<typeof blankImage>, x: number, y: number, digits: string, module: number, height: number): number {
  const elements = ["N", "N", "N", "N"]; // início: barra, espaço, barra, espaço
  for (let i = 0; i < digits.length; i += 2) {
    const bars = ITF[Number(digits[i])];
    const spaces = ITF[Number(digits[i + 1])];
    for (let k = 0; k < 5; k++) elements.push(bars[k], spaces[k]);
  }
  elements.push("W", "N", "N"); // fim
  let cursor = x;
  elements.forEach((element, index) => {
    const size = (element === "W" ? 3 : 1) * module;
    if (index % 2 === 0) paint(image, cursor, y, cursor + size, y + height);
    cursor += size;
  });
  return cursor - x;
}
const BOLETO = "23793381286000000000300000000400184340000010000"; // 44 dígitos + 3 de folga: par

test("código de barras de boleto (ITF) vira uma tarja que cobre as barras", () => {
  const image = blankImage(900, 300);
  const width = itf(image, 60, 120, BOLETO.slice(0, 44), 2, 50);
  const boxes = barcodeBoxes(image);
  assert.equal(boxes.length, 1);
  const [box] = boxes;
  assert.ok(box.x0 <= 60 && box.x1 >= 60 + width, `cobre a largura: ${JSON.stringify(box)} x ${60 + width}`);
  assert.ok(box.y0 <= 120 && box.y1 >= 169, `cobre a altura: ${JSON.stringify(box)}`);
});

test("código de barras fino (módulo de 1 px) e baixo também é achado", () => {
  const image = blankImage(600, 120);
  itf(image, 20, 40, BOLETO.slice(0, 44), 1, 24);
  assert.equal(barcodeBoxes(image).length, 1);
});

test("gráfico de barras, linhas de tabela e bloco escuro não são código de barras", () => {
  const grafico = blankImage(600, 300);
  for (let i = 0; i < 60; i++) paint(grafico, 20 + i * 8, 260 - (20 + ((i * 37) % 200)), 20 + i * 8 + 5, 260);
  assert.deepEqual(barcodeBoxes(grafico), []);
  const tabela = blankImage(600, 300);
  for (let x = 20; x < 580; x += 40) paint(tabela, x, 20, x + 2, 280);
  assert.deepEqual(barcodeBoxes(tabela), []);
  const bloco = blankImage(400, 200);
  paint(bloco, 50, 50, 350, 150);
  assert.deepEqual(barcodeBoxes(bloco), []);
});

test("região que o leitor reconheceu como texto não vira código de barras", () => {
  const image = blankImage(900, 300);
  const width = itf(image, 60, 120, BOLETO.slice(0, 44), 2, 50);
  assert.deepEqual(barcodeBoxes(image, [{ x0: 50, y0: 110, x1: 70 + width, y1: 180 }]), []);
});

// Assinaturas -------------------------------------------------------------------------------------------------------
import { signatureBoxes } from "../src/index.ts";

/** Rabisco: linha de 2 px passando pelos pontos. */
function scribble(image: ReturnType<typeof blankImage>, points: [number, number][]) {
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const steps = Math.max(Math.abs(bx - ax), Math.abs(by - ay));
    for (let s = 0; s <= steps; s++) {
      const x = Math.round(ax + ((bx - ax) * s) / steps);
      const y = Math.round(ay + ((by - ay) * s) / steps);
      paint(image, x, y, x + 2, y + 2);
    }
  }
}
const RABISCO: [number, number][] = [[150, 230], [180, 195], [200, 240], [230, 200], [260, 238], [300, 192], [330, 236],
  [360, 205], [400, 232], [420, 215]];
/** Palavra lida com confiança, com "letras" de tinta dentro da caixa. */
function word(image: ReturnType<typeof blankImage>, text: string, x0: number, y0: number, line: number, confidence = 92): OcrWord {
  const x1 = x0 + text.length * 12;
  for (let x = x0 + 1; x < x1 - 2; x += 6) paint(image, x, y0 + 3, x + 3, y0 + 17);
  return { text, bbox: { x0, y0, x1, y1: y0 + 20 }, line, confidence };
}

test("rabisco acima da linha de assinatura vira tarja; o nome embaixo fica para a detecção de texto", () => {
  const image = blankImage(800, 400);
  paint(image, 100, 250, 500, 252); // a linha
  scribble(image, RABISCO);
  const words = [word(image, "Maria", 150, 258, 1), word(image, "Souza", 230, 258, 1)];
  const boxes = signatureBoxes(image, words);
  assert.equal(boxes.length, 1);
  const [box] = boxes;
  assert.ok(box.x0 <= 150 && box.x1 >= 420 && box.y0 <= 192 && box.y1 >= 240, JSON.stringify(box));
  assert.ok(box.y1 <= 258, `não desce até o nome: ${JSON.stringify(box)}`);
});

test("rabisco ao lado da palavra Assinatura também vira tarja", () => {
  const image = blankImage(800, 300);
  const words = [word(image, "Assinatura:", 40, 100, 0)];
  scribble(image, [[200, 115], [230, 95], [250, 125], [280, 98], [310, 122], [350, 100], [380, 118]]);
  const boxes = signatureBoxes(image, words);
  assert.equal(boxes.length, 1);
  assert.ok(boxes[0].x0 <= 200 && boxes[0].x1 >= 380, JSON.stringify(boxes[0]));
});

test("texto acima de uma linha e rabisco solto não são assinatura", () => {
  const comTexto = blankImage(800, 400);
  paint(comTexto, 100, 250, 500, 252);
  const words = [word(comTexto, "Total", 120, 215, 0), word(comTexto, "do", 200, 215, 0), word(comTexto, "pedido", 240, 215, 0)];
  assert.deepEqual(signatureBoxes(comTexto, words), []);
  const solto = blankImage(800, 400);
  scribble(solto, RABISCO);
  assert.deepEqual(signatureBoxes(solto, []), []);
});
