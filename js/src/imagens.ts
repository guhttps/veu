// Imagens (Véu Pro): o texto de um print vem de um leitor de imagem (OCR) que roda no navegador; aqui, as palavras
// lidas viram um texto, o Véu acha os dados nele, e cada dado vira uma tarja sobre as palavras onde ele aparece.
// Não depende do leitor: recebe as palavras com as caixas e devolve as tarjas. A imagem nunca sai do navegador.
import type { Entity } from "./entities.ts";

export interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Uma palavra lida na imagem: o texto, a caixa (em pixels), a linha em que ela está e a confiança do leitor (0 a 100). */
export interface OcrWord {
  text: string;
  bbox: Box;
  line: number;
  confidence?: number;
}

/** Pixels de uma imagem (RGBA, como o ImageData do canvas). */
export interface PixelImage {
  data: Uint8ClampedArray | Uint8Array;
  width: number;
  height: number;
}

export interface ImageRedaction {
  boxes: Box[]; // uma tarja por dado e por linha, já com margem
  counts: Record<string, number>; // quantos dados de cada tipo
  text: string; // o texto que o Véu analisou (o que o leitor entendeu da imagem)
}

// O leitor costuma trocar o "@" do e-mail por "&", "&M", "®", "©" ou "(a)": "ana&Mexemplo.com.br".
const AT_INSIDE = /^([\p{L}\p{N}._%+-]+)(?:&M|&|®|©|\(a\)|\(at\))([\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)+)$/u;
const AT_END = /^([\p{L}\p{N}._%+-]+)(?:&M|&|®|©|@)$/u;
const DOMAIN = /^M?([\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)+)$/u;

/**
 * Junta as palavras num texto (palavras separadas por espaço, linhas por quebra de linha), conserta o "@" que o
 * leitor errou e devolve, para cada posição do texto, a palavra de onde ela veio (-1 nos espaços).
 */
function assemble(words: readonly OcrWord[]): { text: string; owners: number[] } {
  let text = "";
  const owners: number[] = [];
  const add = (piece: string, owner: number) => {
    text += piece;
    for (let i = 0; i < piece.length; i++) owners.push(owner);
  };
  for (let i = 0; i < words.length; i++) {
    const word = words[i];
    if (i > 0) add(word.line === words[i - 1].line ? " " : "\n", -1);
    const inside = AT_INSIDE.exec(word.text);
    if (inside) {
      add(`${inside[1]}@${inside[2]}`, i);
      continue;
    }
    // "ana&" e "exemplo.com.br" em palavras separadas, na mesma linha: viram um e-mail só.
    const end = AT_END.exec(word.text);
    const next = words[i + 1];
    const domain = next && next.line === word.line ? DOMAIN.exec(next.text) : null;
    if (end && domain) {
      add(`${end[1]}@`, i);
      add(domain[1], i + 1);
      i += 1;
      continue;
    }
    add(word.text, i);
  }
  return { text, owners };
}

/**
 * Tarjas para os dados de um print. `analyze` é o Véu já configurado (tipos desligados, listas próprias):
 * `(texto) => veu.analyze(texto)`. A tarja cobre as palavras inteiras onde o dado aparece, linha por linha.
 */
export function imageRedactions(words: readonly OcrWord[], analyze: (text: string) => Entity[], margin = 3): ImageRedaction {
  const { text, owners } = assemble(words);
  const counts: Record<string, number> = {};
  const boxes: Box[] = [];
  for (const entity of analyze(text)) {
    const covered = new Set<number>();
    for (let position = entity.start; position < entity.end; position++) {
      if (owners[position] >= 0) covered.add(owners[position]);
    }
    if (!covered.size) continue;
    counts[entity.label] = (counts[entity.label] ?? 0) + 1;
    const perLine = new Map<number, Box>();
    for (const index of covered) {
      const { bbox, line } = words[index];
      const box = perLine.get(line);
      perLine.set(line, box
        ? { x0: Math.min(box.x0, bbox.x0), y0: Math.min(box.y0, bbox.y0), x1: Math.max(box.x1, bbox.x1), y1: Math.max(box.y1, bbox.y1) }
        : { ...bbox });
    }
    for (const box of perLine.values()) {
      boxes.push({ x0: box.x0 - margin, y0: box.y0 - margin, x1: box.x1 + margin, y1: box.y1 + margin });
    }
  }
  return { boxes, counts, text };
}

/**
 * Palavras na ordem de leitura a partir do resultado do Tesseract (`recognize(imagem, {}, { blocks: true })`):
 * blocos, parágrafos, linhas e palavras. Cada linha ganha um número próprio.
 */
export function wordsFromTesseract(blocks: readonly { paragraphs: readonly { lines: readonly { words: readonly
  { text: string; bbox: Box; confidence?: number }[] }[] }[] }[] | null | undefined): OcrWord[] {
  const words: OcrWord[] = [];
  let line = 0;
  for (const block of blocks ?? []) {
    for (const paragraph of block.paragraphs) {
      for (const row of paragraph.lines) {
        for (const word of row.words) {
          if (word.text.trim()) words.push({ text: word.text, bbox: word.bbox, line, confidence: word.confidence });
        }
        line += 1;
      }
    }
  }
  return words;
}

// Códigos de barras ------------------------------------------------------------------------------------------------
// Sem decodificar: acha a região de muitas barras verticais escuras, finas, juntas e da mesma altura (boleto, ITF,
// EAN, Code 128) para cobrir com tarja. Gráfico de barras (alturas diferentes, barras coloridas), linhas de tabela
// (espaçadas) e texto (o leitor reconhece as palavras) ficam.

const MIN_BAR_HEIGHT = 10; // px
const MAX_BAR_WIDTH = 14;
const MAX_BAR_GAP = 14;
const MIN_BARS = 14;
const MIN_BARCODE_WIDTH = 50;

/** Tons de cinza (0 a 255) de uma imagem RGBA. */
export function grayscale({ data, width, height }: PixelImage): Uint8Array {
  const gray = new Uint8Array(width * height);
  for (let i = 0, p = 0; i < gray.length; i++, p += 4) gray[i] = (data[p] * 299 + data[p + 1] * 587 + data[p + 2] * 114) / 1000;
  return gray;
}

/**
 * Pixels escuros de tinta: bem mais escuros que a vizinhança (janela de 31 x 31, pela imagem integral) e escuros de
 * verdade (menos de 110 em 255). Funciona em print e em foto com luz desigual; barras coloridas de gráfico ficam de fora.
 */
export function inkPixels(gray: Uint8Array, width: number, height: number): Uint8Array {
  const stride = width + 1;
  const integral = new Int32Array(stride * (height + 1));
  for (let y = 0; y < height; y++) {
    let row = 0;
    for (let x = 0; x < width; x++) {
      row += gray[y * width + x];
      integral[(y + 1) * stride + x + 1] = integral[y * stride + x + 1] + row;
    }
  }
  const ink = new Uint8Array(width * height);
  const radius = 15;
  for (let y = 0; y < height; y++) {
    const top = Math.max(0, y - radius);
    const bottom = Math.min(height, y + radius + 1);
    for (let x = 0; x < width; x++) {
      const value = gray[y * width + x];
      if (value >= 110) continue;
      const left = Math.max(0, x - radius);
      const right = Math.min(width, x + radius + 1);
      const sum = integral[bottom * stride + right] - integral[top * stride + right] - integral[bottom * stride + left]
        + integral[top * stride + left];
      if (value < sum / ((bottom - top) * (right - left)) - 20) ink[y * width + x] = 1;
    }
  }
  return ink;
}

/** Para cada pixel de tinta, a altura do trecho vertical de tinta em que ele está. */
function verticalRuns(ink: Uint8Array, width: number, height: number): Uint16Array {
  const runs = new Uint16Array(width * height);
  for (let x = 0; x < width; x++) {
    let y = 0;
    while (y < height) {
      if (!ink[y * width + x]) {
        y += 1;
        continue;
      }
      let end = y;
      while (end < height && ink[end * width + x]) end += 1;
      const length = Math.min(end - y, 65535);
      for (let k = y; k < end; k++) runs[k * width + x] = length;
      y = end;
    }
  }
  return runs;
}

/** Fração da caixa coberta pelas outras caixas (somadas, sem descontar sobreposições entre elas). */
function coveredFraction(box: Box, others: readonly Box[]): number {
  const area = Math.max(1, (box.x1 - box.x0) * (box.y1 - box.y0));
  let covered = 0;
  for (const other of others) {
    const w = Math.min(box.x1, other.x1) - Math.max(box.x0, other.x0);
    const h = Math.min(box.y1, other.y1) - Math.max(box.y0, other.y0);
    if (w > 0 && h > 0) covered += w * h;
  }
  return covered / area;
}

/**
 * Regiões de código de barras da imagem, com margem. `text` são as caixas das palavras que o leitor reconheceu com
 * confiança: uma região que é quase toda texto não é código de barras.
 */
export function barcodeBoxes(image: PixelImage, text: readonly Box[] = []): Box[] {
  const { width, height } = image;
  const runs = verticalRuns(inkPixels(grayscale(image), width, height), width, height);
  const segments: { x0: number; x1: number; y: number }[] = [];
  for (let y = 0; y < height; y += 2) {
    const base = y * width;
    let bars: [number, number][] = [];
    const flush = () => {
      if (bars.length >= MIN_BARS && bars[bars.length - 1][1] - bars[0][0] >= MIN_BARCODE_WIDTH) {
        segments.push({ x0: bars[0][0], x1: bars[bars.length - 1][1], y });
      }
      bars = [];
    };
    let x = 0;
    while (x < width) {
      if (runs[base + x] < MIN_BAR_HEIGHT) {
        x += 1;
        continue;
      }
      let end = x;
      while (end < width && runs[base + end] >= MIN_BAR_HEIGHT) end += 1;
      if (end - x > MAX_BAR_WIDTH) flush(); // bloco escuro largo: não é barra
      else {
        if (bars.length && x - bars[bars.length - 1][1] > MAX_BAR_GAP) flush();
        bars.push([x, end]);
      }
      x = end;
    }
    flush();
  }
  // Trechos de linhas vizinhas que se sobrepõem viram uma região.
  const regions: { x0: number; x1: number; y0: number; y1: number; rows: { x0: number; x1: number }[] }[] = [];
  for (const segment of segments) {
    const region = regions.find((r) => segment.y - r.y1 <= 4
      && Math.min(r.x1, segment.x1) - Math.max(r.x0, segment.x0) >= 0.5 * Math.min(r.x1 - r.x0, segment.x1 - segment.x0));
    if (region) {
      region.x0 = Math.min(region.x0, segment.x0);
      region.x1 = Math.max(region.x1, segment.x1);
      region.y1 = segment.y;
      region.rows.push(segment);
    } else {
      regions.push({ x0: segment.x0, x1: segment.x1, y0: segment.y, y1: segment.y, rows: [segment] });
    }
  }
  const boxes: Box[] = [];
  for (const region of regions) {
    const regionWidth = region.x1 - region.x0;
    if (region.y1 - region.y0 + 1 < MIN_BAR_HEIGHT || regionWidth < MIN_BARCODE_WIDTH) continue;
    // Num código de barras, as barras têm a mesma altura: quase toda linha da região atravessa a largura inteira.
    // Num gráfico de barras, as linhas de cima só pegam as barras mais altas.
    const fullRows = region.rows.filter((row) => row.x1 - row.x0 >= 0.8 * regionWidth).length;
    if (fullRows < 0.7 * region.rows.length) continue;
    // E cada barra tem a altura da região: num gráfico, a faixa de baixo tem todas as barras, mas elas sobem até
    // alturas diferentes, bem além da faixa.
    const regionHeight = region.y1 - region.y0 + 2;
    const middle = (region.y0 + Math.floor((region.y1 - region.y0) / 4) * 2) * width;
    let bars = 0;
    let fitting = 0;
    for (let x = region.x0; x < region.x1; x++) {
      const run = runs[middle + x];
      if (run < MIN_BAR_HEIGHT || (x > region.x0 && runs[middle + x - 1] >= MIN_BAR_HEIGHT)) continue; // início de barra
      bars += 1;
      if (run >= 0.7 * regionHeight && run <= 1.4 * regionHeight) fitting += 1;
    }
    if (!bars || fitting < 0.75 * bars) continue;
    const box = { x0: Math.max(0, region.x0 - 8), y0: Math.max(0, region.y0 - 4), x1: Math.min(width, region.x1 + 8),
      y1: Math.min(height, region.y1 + 5) };
    if (coveredFraction(box, text) >= 0.3) continue;
    boxes.push(box);
  }
  return boxes;
}

// Assinaturas -------------------------------------------------------------------------------------------------------
// Sem detector de assinatura que caiba no navegador, a regra segue o jeito dos documentos: tinta que o leitor não
// reconhece como palavra, logo acima de uma linha de assinatura (desenhada ou "______") ou ao lado da palavra
// "Assinatura". O nome e o CPF embaixo da linha já são escondidos como texto.

const SIGNATURE_LABEL = /^(assinatura|assinado|assinada|ass\.?|signature|signed|firma)\b/i;
const UNDERSCORES = /^[_.\-]{5,}$/;

/** Palavras lidas com confiança (texto de verdade, não rabisco). */
function confidentBoxes(words: readonly OcrWord[]): Box[] {
  return words.filter((word) => (word.confidence ?? 100) >= 60 && /[\p{L}\p{N}]/u.test(word.text)
    && !SIGNATURE_LABEL.test(word.text)).map((word) => word.bbox);
}

/** Linhas horizontais longas e finas de tinta (a linha de assinatura): { x0, x1, y0, y1 }. */
function horizontalLines(ink: Uint8Array, width: number, height: number, minLength: number): Box[] {
  const lines: Box[] = [];
  for (let y = 0; y < height; y++) {
    let x = 0;
    while (x < width) {
      if (!ink[y * width + x]) {
        x += 1;
        continue;
      }
      let end = x;
      while (end < width && (ink[y * width + end] || (end + 1 < width && ink[y * width + end + 1]))) end += 1;
      if (end - x >= minLength) {
        const line = lines.find((l) => y - l.y1 <= 1 && Math.min(l.x1, end) - Math.max(l.x0, x) >= 0.8 * (end - x));
        if (line) {
          line.y1 = y;
          line.x0 = Math.min(line.x0, x);
          line.x1 = Math.max(line.x1, end);
        } else {
          lines.push({ x0: x, x1: end, y0: y, y1: y });
        }
      }
      x = end + 1;
    }
  }
  return lines.filter((line) => line.y1 - line.y0 <= 6); // fina: borda de tabela grossa ou bloco não contam
}

/** Máscara das caixas (com 2 px de folga): 1 dentro de alguma delas. */
function boxMask(boxes: readonly Box[], width: number, height: number): Uint8Array {
  const mask = new Uint8Array(width * height);
  for (const box of boxes) {
    const x0 = Math.max(0, Math.floor(box.x0) - 2);
    const x1 = Math.min(width, Math.ceil(box.x1) + 2);
    for (let y = Math.max(0, Math.floor(box.y0) - 2); y < Math.min(height, Math.ceil(box.y1) + 2); y++) {
      mask.fill(1, y * width + x0, y * width + Math.max(x0, x1));
    }
  }
  return mask;
}

/** Caixa da tinta "solta" (fora das palavras lidas com confiança e fora das linhas) dentro da área, ou null. */
function looseInk(ink: Uint8Array, width: number, height: number, area: Box, skip: Uint8Array): Box | null {
  const x0 = Math.max(0, Math.floor(area.x0));
  const x1 = Math.min(width, Math.ceil(area.x1));
  const y0 = Math.max(0, Math.floor(area.y0));
  const y1 = Math.min(height, Math.ceil(area.y1));
  if (x1 <= x0 || y1 <= y0) return null;
  let count = 0;
  const found = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      if (!ink[y * width + x] || skip[y * width + x]) continue;
      count += 1;
      found.x0 = Math.min(found.x0, x);
      found.x1 = Math.max(found.x1, x + 1);
      found.y0 = Math.min(found.y0, y);
      found.y1 = Math.max(found.y1, y + 1);
    }
  }
  // Rabisco de verdade: tinta suficiente e espalhada (um ponto ou um risco curto não é assinatura).
  if (count < 40 || found.x1 - found.x0 < 30 || found.y1 - found.y0 < 8) return null;
  return found;
}

/** Regiões de assinatura da imagem (com margem). `words` são as palavras lidas pelo leitor, com a confiança. */
export function signatureBoxes(image: PixelImage, words: readonly OcrWord[]): Box[] {
  const { width, height } = image;
  const ink = inkPixels(grayscale(image), width, height);
  const text = confidentBoxes(words);
  const heights = words.map((word) => word.bbox.y1 - word.bbox.y0).sort((a, b) => a - b);
  const lineHeight = Math.max(12, heights.length ? heights[Math.floor(heights.length / 2)] : 20);
  const lines = horizontalLines(ink, width, height, Math.max(100, Math.round(width * 0.12)));
  for (const word of words) if (UNDERSCORES.test(word.text)) lines.push({ ...word.bbox, y0: word.bbox.y1 - 3 });
  const skip = boxMask([...text, ...lines.map((line) => ({ ...line, y0: line.y0 - 1, y1: line.y1 + 2 }))], width, height);
  const areas: Box[] = [];
  // Acima de cada linha de assinatura, até três linhas de texto de altura.
  for (const line of lines) areas.push({ x0: line.x0 - lineHeight, y0: line.y0 - 4 * lineHeight, x1: line.x1 + lineHeight, y1: line.y1 + 2 });
  // Ao lado e embaixo da palavra "Assinatura".
  for (const word of words) {
    if (!SIGNATURE_LABEL.test(word.text)) continue;
    const { bbox } = word;
    const h = bbox.y1 - bbox.y0;
    areas.push({ x0: bbox.x1 + 2, y0: bbox.y0 - 2 * h, x1: bbox.x1 + 16 * h, y1: bbox.y1 + 2 * h });
    areas.push({ x0: bbox.x0 - h, y0: bbox.y1 + 2, x1: bbox.x0 + 16 * h, y1: bbox.y1 + 4 * h });
  }
  const boxes: Box[] = [];
  for (const area of areas) {
    const found = looseInk(ink, width, height, area, skip);
    if (!found) continue;
    const box = { x0: Math.max(0, found.x0 - 6), y0: Math.max(0, found.y0 - 6), x1: Math.min(width, found.x1 + 6),
      y1: Math.min(height, found.y1 + 6) };
    if (!boxes.some((other) => coveredFraction(box, [other]) > 0.8)) boxes.push(box);
  }
  return boxes;
}
