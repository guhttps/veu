// Word, Excel e PowerPoint no navegador (equivalente a documents.py): o arquivo volta no mesmo formato, com os
// dados trocados por marcadores e a formatação preservada. Sem dependências: o zip é lido e gravado aqui, com
// DecompressionStream e CompressionStream ("deflate-raw"), que navegadores e Node já têm.
import type { Veu } from "./index.ts";
import type { Vault } from "./vault.ts";

export type DocumentKind = "docx" | "xlsx" | "pptx";

// Um .docx de 300 KB pode guardar 300 MB de XML (zip bomb): os tamanhos declarados são conferidos antes.
export const MAX_UNZIPPED = 200 * 1024 * 1024;
export const MAX_RATIO = 100;

// Zip -----------------------------------------------------------------------------------------------------------

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

type ByteStream = ReadableWritablePair<Uint8Array, Uint8Array>;
const deflate = (mode: "compress" | "decompress"): ByteStream =>
  (mode === "compress" ? new CompressionStream("deflate-raw") : new DecompressionStream("deflate-raw")) as unknown as ByteStream;

async function transform(bytes: Uint8Array, stream: ByteStream, limit: number): Promise<Uint8Array> {
  const reader = new Blob([bytes as BlobPart]).stream().pipeThrough(stream).getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > limit) {
      await reader.cancel();
      throw new Error("Arquivo suspeito: cresce mais que o declarado ao abrir (zip bomb).");
    }
    chunks.push(value);
  }
  const output = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

/** Arquivos do zip, na ordem original. Recusa zip bomb antes de descompactar. */
export async function readZip(bytes: Uint8Array): Promise<Map<string, Uint8Array>> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65535); i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      end = i;
      break;
    }
  }
  if (end < 0) throw new Error("Não é um arquivo do Office válido (zip sem diretório).");
  const count = view.getUint16(end + 10, true);
  let pointer = view.getUint32(end + 16, true);
  const entries: { name: string; method: number; size: number; packed: number; offset: number }[] = [];
  let total = 0;
  for (let i = 0; i < count; i++) {
    if (view.getUint32(pointer, true) !== 0x02014b50) throw new Error("Zip corrompido.");
    const method = view.getUint16(pointer + 10, true);
    const packed = view.getUint32(pointer + 20, true);
    const size = view.getUint32(pointer + 24, true);
    const nameLength = view.getUint16(pointer + 28, true);
    const extra = view.getUint16(pointer + 30, true);
    const comment = view.getUint16(pointer + 32, true);
    const offset = view.getUint32(pointer + 42, true);
    const name = new TextDecoder().decode(bytes.subarray(pointer + 46, pointer + 46 + nameLength));
    total += size;
    if (size > 1024 * 1024 && size > MAX_RATIO * Math.max(packed, 1)) {
      throw new Error(`Arquivo suspeito: ${name} cresce mais de ${MAX_RATIO} vezes ao abrir (zip bomb).`);
    }
    entries.push({ name, method, size, packed, offset });
    pointer += 46 + nameLength + extra + comment;
  }
  if (total > MAX_UNZIPPED) throw new Error(`Arquivo grande demais: mais de ${MAX_UNZIPPED / 1024 / 1024} MB ao abrir.`);
  const files = new Map<string, Uint8Array>();
  for (const entry of entries) {
    if (view.getUint32(entry.offset, true) !== 0x04034b50) throw new Error("Zip corrompido.");
    const start = entry.offset + 30 + view.getUint16(entry.offset + 26, true) + view.getUint16(entry.offset + 28, true);
    const data = bytes.subarray(start, start + entry.packed);
    if (entry.name.endsWith("/")) continue;
    if (entry.method === 0) files.set(entry.name, data.slice());
    else if (entry.method === 8) files.set(entry.name, await transform(data, deflate("decompress"), entry.size));
    else throw new Error(`Compressão não suportada em ${entry.name}.`);
  }
  return files;
}

/** Zip com deflate, na ordem dada. */
export async function writeZip(files: Map<string, Uint8Array>): Promise<Uint8Array> {
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const [name, data] of files) {
    const encodedName = new TextEncoder().encode(name);
    const packed = await transform(data, deflate("compress"), Number.MAX_SAFE_INTEGER);
    const crc = crc32(data);
    const local = new Uint8Array(30 + encodedName.length);
    const view = new DataView(local.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true); // nomes em UTF-8
    view.setUint16(8, 8, true);
    view.setUint16(12, 0x5821, true); // 1/1/2024, fixo: o mesmo arquivo dá os mesmos bytes
    view.setUint32(14, crc, true);
    view.setUint32(18, packed.length, true);
    view.setUint32(22, data.length, true);
    view.setUint16(26, encodedName.length, true);
    local.set(encodedName, 30);
    const header = new Uint8Array(46 + encodedName.length);
    const headerView = new DataView(header.buffer);
    headerView.setUint32(0, 0x02014b50, true);
    headerView.setUint16(4, 20, true);
    headerView.setUint16(6, 20, true);
    headerView.setUint16(8, 0x0800, true);
    headerView.setUint16(10, 8, true);
    headerView.setUint16(14, 0x5821, true);
    headerView.setUint32(16, crc, true);
    headerView.setUint32(20, packed.length, true);
    headerView.setUint32(24, data.length, true);
    headerView.setUint16(28, encodedName.length, true);
    headerView.setUint32(42, offset, true);
    header.set(encodedName, 46);
    parts.push(local, packed);
    central.push(header);
    offset += local.length + packed.length;
  }
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, files.size, true);
  endView.setUint16(10, files.size, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  const all = [...parts, ...central, end];
  const output = new Uint8Array(all.reduce((sum, part) => sum + part.length, 0));
  let position = 0;
  for (const part of all) {
    output.set(part, position);
    position += part.length;
  }
  return output;
}

// XML ------------------------------------------------------------------------------------------------------------

export interface Span {
  start: number;
  end: number;
  replacement: string;
}

const decodeXml = (text: string): string => text.replace(/&(lt|gt|amp|quot|apos|#\d+|#x[0-9a-fA-F]+);/g, (entity, name: string) => {
  if (name[0] === "#") return String.fromCodePoint(name[1] === "x" ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10));
  return ({ lt: "<", gt: ">", amp: "&", quot: '"', apos: "'" } as Record<string, string>)[name] ?? entity;
});
const encodeXml = (text: string): string => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const TAG = /<(\/?)(?:([\w.-]+):)?([\w.-]+)((?:\s[^>]*?)?)(\/?)>/g;
const BREAKS = new Set(["tab", "br", "cr"]);

interface TextNode {
  tagEnd: number; // fim da tag de abertura
  closeStart: number; // início da tag de fechamento
  openTag: string;
  text: string;
  gap: boolean; // tabulação ou quebra de linha antes deste trecho, no mesmo parágrafo
}

/**
 * Reescreve o texto de um XML do Office parágrafo por parágrafo: os trechos de texto (w:t, a:t, t) de cada parágrafo
 * (w:p, a:p, si, is) são juntados, spansOf diz o que trocar, e cada troca fica no trecho onde o dado começava. Assim,
 * um nome dividido pela formatação ("Ma" em negrito e "ria") é encontrado, e a formatação continua no lugar.
 */
export function rewriteXml(xml: string, paragraphs: ReadonlySet<string>, spansOf: (text: string) => Span[]): string {
  const stack: TextNode[][] = [];
  const groups: TextNode[][] = [];
  let pendingGap = false;
  TAG.lastIndex = 0;
  for (let match = TAG.exec(xml); match !== null; match = TAG.exec(xml)) {
    const [whole, closing, prefix, local, , selfClosing] = match;
    if (paragraphs.has(local)) {
      if (selfClosing) continue;
      if (closing) {
        const group = stack.pop();
        if (group?.length) groups.push(group);
      } else {
        stack.push([]);
      }
      pendingGap = false;
    } else if (BREAKS.has(local) && !closing) {
      pendingGap = true;
    } else if (local === "t" && !closing && !selfClosing && stack.length) {
      const close = xml.indexOf(`</${prefix ? `${prefix}:` : ""}t>`, match.index + whole.length);
      if (close < 0) break;
      stack[stack.length - 1].push({ tagEnd: match.index + whole.length, closeStart: close, openTag: whole,
        text: decodeXml(xml.slice(match.index + whole.length, close)), gap: pendingGap });
      pendingGap = false;
      TAG.lastIndex = close;
    }
  }
  const edits: [number, number, string][] = [];
  for (const nodes of groups) {
    const chars: string[] = [];
    const owners: number[] = [];
    nodes.forEach((node, index) => {
      if (node.gap && chars.length) {
        chars.push(" ");
        owners.push(-1); // separador só para a detecção: não volta para o arquivo
      }
      for (const char of node.text) {
        chars.push(char);
        owners.push(index);
      }
    });
    const spans = spansOf(chars.join(""));
    if (!spans.length) continue;
    // Posições em code units (as do JavaScript) para caracteres: os spans vêm em code units.
    const unitsToChars: number[] = [];
    let units = 0;
    for (let i = 0; i < chars.length; i++) {
      unitsToChars[units] = i;
      units += chars[i].length;
    }
    unitsToChars[units] = chars.length;
    for (const span of [...spans].sort((a, b) => b.start - a.start)) {
      const start = unitsToChars[span.start] ?? chars.length;
      const end = unitsToChars[span.end] ?? chars.length;
      let owner = owners.slice(start).find((value) => value >= 0);
      if (owner === undefined) owner = [...owners].reverse().find((value) => value >= 0) ?? 0;
      const replacement = [...span.replacement];
      chars.splice(start, end - start, ...replacement);
      owners.splice(start, end - start, ...replacement.map(() => owner));
    }
    const texts = nodes.map(() => [] as string[]);
    chars.forEach((char, i) => {
      if (owners[i] >= 0) texts[owners[i]].push(char);
    });
    nodes.forEach((node, index) => {
      const joined = texts[index].join("");
      if (joined === node.text) return;
      let openTag = node.openTag;
      if (/^\s|\s$/.test(joined) && !/xml:space=/.test(openTag)) openTag = openTag.replace(/(\/?)>$/, ' xml:space="preserve">');
      edits.push([node.tagEnd - node.openTag.length, node.closeStart, openTag + encodeXml(joined)]);
    });
  }
  let output = xml;
  for (const [start, end, value] of edits.sort((a, b) => b[0] - a[0])) output = output.slice(0, start) + value + output.slice(end);
  return output;
}

// Excel: números que são documentos (CPF, cartão) viram texto com o marcador.
function rewriteNumberCells(xml: string, valueOf: (digits: string) => string | null): string {
  return xml.replace(/<c\b([^>]*?)(?<!\/)>(<v>(\d{8,19})<\/v>)<\/c>/g, (whole, attributes: string, _v, digits: string) => {
    if (/\bt="(?!n")/.test(attributes)) return whole;
    const replacement = valueOf(digits);
    if (replacement === null) return whole;
    return `<c${attributes.replace(/\s+t="n"/, "")} t="inlineStr"><is><t>${encodeXml(replacement)}</t></is></c>`;
  });
}

const PARTS: Record<DocumentKind, { test: RegExp; paragraphs: ReadonlySet<string> }[]> = {
  docx: [{ test: /^word\/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$/, paragraphs: new Set(["p"]) }],
  pptx: [{ test: /^ppt\/(slides\/slide\d+|notesSlides\/notesSlide\d+)\.xml$/, paragraphs: new Set(["p"]) }],
  xlsx: [{ test: /^xl\/(sharedStrings|worksheets\/sheet\d+)\.xml$/, paragraphs: new Set(["si", "is"]) }],
};

export function documentKind(name: string): DocumentKind | null {
  const extension = name.toLowerCase().split(".").pop();
  return extension === "docx" || extension === "xlsx" || extension === "pptx" ? extension : null;
}

async function rewriteDocument(bytes: Uint8Array, kind: DocumentKind, spansOf: (text: string) => Span[],
  numbers?: (digits: string) => string | null): Promise<Uint8Array> {
  const files = await readZip(bytes);
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  for (const [name, data] of files) {
    if (name === "docProps/core.xml") {
      // Autor e quem salvou por último: o nome de quem fez o arquivo também é um dado pessoal.
      const xml = decoder.decode(data).replace(/(<dc:creator>|<cp:lastModifiedBy>)[^<]*(<\/)/g, "$1$2");
      files.set(name, encoder.encode(xml));
      continue;
    }
    const part = PARTS[kind].find((candidate) => candidate.test.test(name));
    if (!part) continue;
    let xml = rewriteXml(decoder.decode(data), part.paragraphs, spansOf);
    if (numbers && name.startsWith("xl/worksheets/")) xml = rewriteNumberCells(xml, numbers);
    files.set(name, encoder.encode(xml));
  }
  return writeZip(files);
}

/** Protege um documento do Office com o cofre dado: { bytes, counts } (quantos dados de cada tipo). */
export async function protectDocument(bytes: Uint8Array, kind: DocumentKind, veu: Veu, vault: Vault):
  Promise<{ bytes: Uint8Array; counts: Record<string, number> }> {
  const counts: Record<string, number> = {};
  const count = (label: string) => { counts[label] = (counts[label] || 0) + 1; };
  const spansOf = (text: string): Span[] => {
    if (!text.trim()) return [];
    return veu.anonymize(text, vault).replacements.map((item) => {
      count(item.entity.label);
      return { start: item.entity.start, end: item.entity.end, replacement: item.replacement };
    });
  };
  const numbers = (digits: string): string | null => {
    const result = veu.anonymize(digits, vault);
    const whole = result.replacements.find((item) => item.entity.start === 0 && item.entity.end === digits.length);
    if (!whole) return null;
    count(whole.entity.label);
    return whole.replacement;
  };
  return { bytes: await rewriteDocument(bytes, kind, spansOf, kind === "xlsx" ? numbers : undefined), counts };
}

const MARKER = /\[[A-Z]+(?:_[A-Z]+)*_[0-9a-fA-F]{1,16}\]/g;

/** Devolve os dados reais a um documento que voltou da IA (ou que o Véu protegeu). */
export async function restoreDocument(bytes: Uint8Array, kind: DocumentKind, vault: Vault): Promise<Uint8Array> {
  const spansOf = (text: string): Span[] => [...text.matchAll(MARKER)].flatMap((match) => {
    const value = vault.restore(match[0]);
    return value === match[0] ? [] : [{ start: match.index!, end: match.index! + match[0].length, replacement: value }];
  });
  return rewriteDocument(bytes, kind, spansOf);
}
