// Listas próprias: termos que sempre são escondidos (equivalente a recognizers/terms.py).
// A busca ignora maiúsculas e acentos e respeita palavras inteiras; espaços no termo aceitam qualquer espaço.
import type { Candidate, Recognizer } from "./entities.ts";
import { escapeRegex } from "./text.ts";

const foldCache = new Map<string, string>();

function foldChar(char: string): string {
  let value = foldCache.get(char);
  if (value === undefined) {
    const base = char.normalize("NFD")[0].toLowerCase();
    value = base.length === 1 ? base : char;
    foldCache.set(char, value);
  }
  return value;
}

/** Minúsculas e sem acentos, caractere por caractere: as posições não mudam. */
export function foldKeepingPositions(text: string): string {
  let output = "";
  for (let i = 0; i < text.length; i++) output += foldChar(text[i]);
  return output;
}

const termPattern = (term: string): string =>
  foldKeepingPositions(term).split(/\s+/).filter(Boolean).map(escapeRegex).join("\\s+");

export class TermRecognizer implements Recognizer {
  name = "termos";
  labels: ReadonlySet<string>;
  private patterns: [string, RegExp][] = [];

  /** {"PESSOA": ["Joana Prado"], "TERMO": ["Projeto Netuno"]} */
  constructor(terms: Record<string, readonly string[]>) {
    for (const [label, values] of Object.entries(terms)) {
      const parts = [...new Set(values.filter((value) => value.trim().length >= 2).map(termPattern))]
        .sort((a, b) => b.length - a.length);
      if (parts.length) {
        this.patterns.push([label.toUpperCase(), new RegExp(`(?<![\\p{L}\\p{N}_])(?:${parts.join("|")})(?![\\p{L}\\p{N}_])`, "gu")]);
      }
    }
    this.labels = new Set(this.patterns.map(([label]) => label));
  }

  *find(text: string): Iterable<Candidate> {
    if (!this.patterns.length) return;
    const folded = foldKeepingPositions(text);
    for (const [label, pattern] of this.patterns) {
      for (const match of folded.matchAll(pattern)) {
        yield { label, start: match.index!, end: match.index! + match[0].length, score: 0.99, recognizer: this.name };
      }
    }
  }
}
