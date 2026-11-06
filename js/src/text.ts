// Funções de texto compartilhadas pelos detectores (equivalentes às de veu/_text.py e recognizers/base.py).

/** Letra, número ou sublinhado em qualquer alfabeto: o \w do Python, que no JavaScript só cobre ASCII. */
export const W = "[\\p{L}\\p{N}_]";

const SPACES = /\s+/gu;
const MARKS = /\p{M}/gu;

export function stripAccents(text: string): string {
  return text.normalize("NFKD").replace(MARKS, "");
}

/** Forma de comparação: minúsculas, sem acentos e com espaços simples. */
export function fold(text: string): string {
  return stripAccents(text).toLowerCase().replace(/ß/g, "ss").replace(SPACES, " ").trim();
}

export function onlyDigits(text: string): string {
  return text.replace(/\D/g, "");
}

export function escapeRegex(text: string): string {
  // Sem o "-": com a flag u, "\-" fora de uma classe é erro de sintaxe (e "-" ali não é especial).
  return text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

/** Regex que acha qualquer uma das palavras (já normalizadas com fold) como palavra inteira. */
export function wordsRegex(words: Iterable<string>): RegExp | null {
  const terms = [...new Set([...words].filter(Boolean).map(fold))].sort((a, b) => b.length - a.length);
  if (!terms.length) return null;
  return new RegExp(`(?<![\\p{L}\\p{N}_/])(?:${terms.map(escapeRegex).join("|")})(?![\\p{L}\\p{N}_/])`, "u");
}

const ALNUM = /[\p{L}\p{N}]/u;

export function isAlnum(char: string | undefined): boolean {
  return char !== undefined && char !== "" && ALNUM.test(char);
}

export function isUpper(text: string): boolean {
  return text !== text.toLowerCase() && text === text.toUpperCase();
}

export function isLower(text: string): boolean {
  return text !== text.toUpperCase() && text === text.toLowerCase();
}

export function isAlpha(text: string): boolean {
  return text.length > 0 && /^\p{L}+$/u.test(text);
}

/** Até size caracteres antes de start, sem começar no meio de uma palavra. */
export function textBefore(text: string, start: number, size: number): string {
  let left = Math.max(0, start - size);
  if (left > 0 && isAlnum(text[left - 1])) {
    while (left < start && isAlnum(text[left])) left += 1;
  }
  return text.slice(left, start);
}

/** Até size caracteres depois de end, sem terminar no meio de uma palavra. */
export function textAfter(text: string, end: number, size: number): string {
  let right = Math.min(text.length, end + size);
  if (right < text.length && isAlnum(text[right])) {
    while (right > end && isAlnum(text[right - 1])) right -= 1;
  }
  return text.slice(end, right);
}

export function contextWindow(text: string, start: number, end: number, before: number, after: number): string {
  return `${fold(textBefore(text, start, before))} │ ${fold(textAfter(text, end, after))}`;
}

/** Torna letras de um trecho de regex insensíveis à caixa ("Rua" -> "[Rr][Uu][Aa]"), sem a flag i. */
export function caseless(source: string): string {
  let output = "";
  let inClass = false;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\\") {
      output += char + (source[i + 1] ?? "");
      i += 1;
      continue;
    }
    if (inClass) {
      if (char === "]") inClass = false;
      const lower = char.toLowerCase();
      const upper = char.toUpperCase();
      output += lower !== upper && char !== "]" ? lower + upper : char;
      continue;
    }
    if (char === "[") {
      inClass = true;
      output += char;
      continue;
    }
    const lower = char.toLowerCase();
    const upper = char.toUpperCase();
    output += lower !== upper ? `[${upper}${lower}]` : char;
  }
  return output;
}

export function counter<T extends string>(items: Iterable<T>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) counts[item] = (counts[item] ?? 0) + 1;
  return counts;
}

/** Busca binária: posição onde value entraria em sorted mantendo a ordem (à direita dos iguais). */
export function bisectRight(sorted: readonly number[], value: number): number {
  let low = 0;
  let high = sorted.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (value < sorted[middle]) high = middle;
    else low = middle + 1;
  }
  return low;
}

export function bisectLeft(sorted: readonly number[], value: number): number {
  let low = 0;
  let high = sorted.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (sorted[middle] < value) low = middle + 1;
    else high = middle;
  }
  return low;
}
