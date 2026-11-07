// Junta os detectores, filtra pela pontuação e resolve sobreposições (equivalente a veu/analyzer.py).
import { DetectionCache } from "./cache.ts";
import { AddressRecognizer } from "./addresses.ts";
import type { Candidate, Entity, Recognizer } from "./entities.ts";
import { PatternRecognizer } from "./patterns.ts";
import { PersonRecognizer } from "./persons.ts";
import { SecretRecognizer } from "./secrets.ts";
import { bisectLeft, fold, onlyDigits } from "./text.ts";
import { normalizeCnpj } from "./validators.ts";

export const DEFAULT_THRESHOLD = 0.5;

export function defaultRecognizers(): Recognizer[] {
  return [new PatternRecognizer(), new PersonRecognizer(), new AddressRecognizer(), new SecretRecognizer()];
}

export interface AnalyzerOptions {
  /** Pontuação mínima de 0 a 1 (padrão 0,5). */
  threshold?: number;
  /** Limita a detecção a alguns tipos (por padrão, todos). */
  labels?: Iterable<string>;
  /** Valores que nunca são escondidos (dados da própria empresa, contatos públicos). */
  allowlist?: Iterable<string>;
  /** Expressões regulares: valores que casarem nunca são escondidos. */
  allowPatterns?: Iterable<string | RegExp>;
  /** Itens no cache de detecção de textos longos (padrão 2048; 0 desliga). */
  cache?: number;
}

export class Analyzer {
  recognizers: Recognizer[];
  /** Cache de detecção (null quando desligado). */
  readonly cache: DetectionCache | null;
  threshold: number;
  labels: Set<string> | null;
  private allowText: Set<string>;
  private allowCodes: Set<string>;
  private allowPatterns: RegExp[];
  private hasAllowlist: boolean;

  constructor(recognizers?: Recognizer[], options: AnalyzerOptions = {}) {
    this.recognizers = recognizers ?? defaultRecognizers();
    const size = options.cache ?? 2048;
    this.cache = size > 0 ? new DetectionCache(size) : null;
    this.threshold = options.threshold ?? DEFAULT_THRESHOLD;
    const labels = options.labels ? [...options.labels] : [];
    this.labels = labels.length ? new Set(labels.map((label) => label.toUpperCase())) : null;
    const allowlist = [...(options.allowlist ?? [])];
    this.allowText = new Set(allowlist.map(fold));
    this.allowCodes = new Set(allowlist.map(onlyDigits).filter((digits) => digits.length >= 6));
    for (const value of allowlist) {
      const cnpj = normalizeCnpj(value);
      if (cnpj.length === 14) this.allowCodes.add(cnpj);
    }
    this.allowPatterns = [...(options.allowPatterns ?? [])].map((p) => (typeof p === "string" ? new RegExp(p, "iu") : p));
    this.hasAllowlist = this.allowText.size > 0 || this.allowCodes.size > 0 || this.allowPatterns.length > 0;
  }

  private allowed(value: string): boolean {
    if (this.allowText.has(fold(value))) return true;
    if (this.allowPatterns.some((pattern) => pattern.test(value))) return true;
    const digits = onlyDigits(value);
    return (digits.length >= 6 && this.allowCodes.has(digits)) || this.allowCodes.has(normalizeCnpj(value));
  }

  candidates(text: string, threshold?: number): Candidate[] {
    const minimum = threshold ?? this.threshold;
    const found: Candidate[] = [];
    for (const recognizer of this.recognizers) {
      for (const candidate of recognizer.find(text)) {
        if (candidate.score < minimum) continue;
        if (this.labels !== null && !this.labels.has(candidate.label)) continue;
        if (this.hasAllowlist && this.allowed(text.slice(candidate.start, candidate.end))) continue;
        found.push(candidate);
      }
    }
    return found;
  }

  analyze(text: string, threshold?: number): Entity[] {
    const cache = this.cache && this.cache.usable(text) ? this.cache : null;
    const extra = threshold === undefined ? "" : String(threshold);
    if (cache) {
      const found = cache.get(text, extra);
      if (found) return found.map((c) => ({ ...c, text: text.slice(c.start, c.end) }));
    }
    if (cache && text) {
      const chosen = resolveOverlaps(this.candidates(text, threshold));
      cache.put(text, chosen, extra);
      return chosen.map((c) => ({ ...c, text: text.slice(c.start, c.end) }));
    }
    if (!text) return [];
    return resolveOverlaps(this.candidates(text, threshold)).map((c) => ({ ...c, text: text.slice(c.start, c.end) }));
  }
}

/** Um candidato por trecho: o contido em outro maior sai; nas sobreposições vence a maior pontuação. */
export function resolveOverlaps(candidates: Candidate[]): Candidate[] {
  const ordered = [...candidates].sort((a, b) => a.start - b.start || b.end - a.end || b.score - a.score);
  const uncontained: Candidate[] = [];
  let container: Candidate | null = null;
  for (const candidate of ordered) {
    if (container !== null && candidate.end <= container.end
      && !(candidate.start === container.start && candidate.end === container.end)) continue;
    uncontained.push(candidate);
    if (container === null || candidate.end > container.end) container = candidate;
  }
  const starts: number[] = [];
  const ends: number[] = [];
  const chosen: Candidate[] = [];
  const byPriority = [...uncontained].sort(
    (a, b) => b.score - a.score || (b.end - b.start) - (a.end - a.start) || a.start - b.start,
  );
  for (const candidate of byPriority) {
    const position = bisectLeft(starts, candidate.start);
    if (position > 0 && ends[position - 1] > candidate.start) continue;
    if (position < starts.length && starts[position] < candidate.end) continue;
    starts.splice(position, 0, candidate.start);
    ends.splice(position, 0, candidate.end);
    chosen.push(candidate);
  }
  return chosen.sort((a, b) => a.start - b.start);
}
