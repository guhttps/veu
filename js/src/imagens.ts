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

/** Uma palavra lida na imagem: o texto, a caixa (em pixels) e a linha em que ela está. */
export interface OcrWord {
  text: string;
  bbox: Box;
  line: number;
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
  { text: string; bbox: Box }[] }[] }[] }[] | null | undefined): OcrWord[] {
  const words: OcrWord[] = [];
  let line = 0;
  for (const block of blocks ?? []) {
    for (const paragraph of block.paragraphs) {
      for (const row of paragraph.lines) {
        for (const word of row.words) {
          if (word.text.trim()) words.push({ text: word.text, bbox: word.bbox, line });
        }
        line += 1;
      }
    }
  }
  return words;
}
