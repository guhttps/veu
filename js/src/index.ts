// Véu para JavaScript e TypeScript: esconde dados pessoais e segredos antes de o texto chegar a um modelo de IA.
import { AddressRecognizer } from "./addresses.ts";
import { Analyzer, type AnalyzerOptions } from "./analyzer.ts";
import { AnonymizationResult, Anonymizer, type AnonymizerOptions } from "./anonymizer.ts";
import type { Entity, Recognizer } from "./entities.ts";
import { PatternRecognizer, customPattern, DEFAULT_SPECS, type PatternSpec } from "./patterns.ts";
import { PersonRecognizer } from "./persons.ts";
import { SecretRecognizer } from "./secrets.ts";
import { counter } from "./text.ts";
import { StreamRestorer, Vault } from "./vault.ts";

export { Analyzer, resolveOverlaps, defaultRecognizers } from "./analyzer.ts";
export { AnonymizationResult, Anonymizer, maskValue, normalizeOperator, OPERATORS } from "./anonymizer.ts";
export type { Operator, Replacement } from "./anonymizer.ts";
export { LABELS, SECRET_LABELS } from "./entities.ts";
export type { Candidate, Entity, Recognizer } from "./entities.ts";
export { AddressRecognizer } from "./addresses.ts";
export { PatternRecognizer, customPattern, DEFAULT_SPECS } from "./patterns.ts";
export { PersonRecognizer } from "./persons.ts";
export { SecretRecognizer, keyKind, looksRandom, secretPrefix } from "./secrets.ts";
export { DetectionCache } from "./cache.ts";
export { StreamRestorer, Vault, linkContext, neutralizePlaceholders, normalizeValue, restoreAllowed, urlHost } from "./vault.ts";
export type { RestoreContext, RestorePolicy, VaultData, VaultEntry } from "./vault.ts";
export * as validators from "./validators.ts";

export const VERSION = "0.6.0";

export const DETECTORS = ["padroes", "nomes", "enderecos", "segredos"] as const;
export type Detector = (typeof DETECTORS)[number];

/** Padrão próprio, como no [[deteccao.personalizados]] do veu.toml. */
export interface CustomPatternOptions {
  entidade: string;
  padrao: string;
  pontuacao?: number;
  contexto?: string[];
  exigeContexto?: boolean;
}

export interface VeuOptions extends AnalyzerOptions, AnonymizerOptions {
  /** Detectores ligados (padrão: todos). */
  detectors?: Detector[];
  /** Padrões próprios. */
  customPatterns?: CustomPatternOptions[];
  /** Detectores extras, somados aos padrões. */
  extraRecognizers?: Recognizer[];
  /** Avisa o modelo para repetir os marcadores (usado pelas integrações). */
  instructModel?: boolean;
  /** Tipos que fazem a requisição ser recusada em vez de escondida (usado pelas integrações). */
  block?: string[];
}

function buildRecognizers(options: VeuOptions): Recognizer[] {
  const detectors = options.detectors ?? [...DETECTORS];
  const custom: PatternSpec[] = (options.customPatterns ?? []).map((p) =>
    customPattern(p.entidade, p.padrao, p.pontuacao ?? 0.9, p.contexto ?? [], p.exigeContexto ?? false));
  const recognizers: Recognizer[] = [];
  for (const name of detectors) {
    if (name === "padroes") recognizers.push(new PatternRecognizer([...DEFAULT_SPECS, ...custom]));
    else if (name === "nomes") recognizers.push(new PersonRecognizer());
    else if (name === "enderecos") recognizers.push(new AddressRecognizer());
    else if (name === "segredos") recognizers.push(new SecretRecognizer());
    else throw new Error(`Detector desconhecido: "${name}". Use um de ${DETECTORS.join(", ")}.`);
  }
  if (custom.length && !detectors.includes("padroes")) recognizers.push(new PatternRecognizer(custom));
  return [...recognizers, ...(options.extraRecognizers ?? [])];
}

/**
 * Ponto de entrada da biblioteca.
 *
 * ```ts
 * const veu = new Veu();
 * const resultado = veu.anonymize("CPF 529.982.247-25");
 * resultado.text;                                   // "CPF [CPF_1]"
 * veu.restore("Seu CPF é [CPF_1]", resultado.vault); // "Seu CPF é 529.982.247-25"
 * ```
 */
export class Veu {
  readonly options: VeuOptions;
  readonly analyzer: Analyzer;
  readonly anonymizer: Anonymizer;

  constructor(options: VeuOptions = {}) {
    this.options = { instructModel: true, ...options };
    this.analyzer = new Analyzer(buildRecognizers(options), options);
    this.anonymizer = new Anonymizer(this.analyzer, options);
  }

  analyze(text: string): Entity[] {
    return this.analyzer.analyze(text);
  }

  anonymize(text: string, vault?: Vault): AnonymizationResult {
    return this.anonymizer.anonymize(text, vault);
  }

  restore(text: string, vault: Vault): string {
    return vault.restore(text);
  }

  newVault(): Vault {
    return this.anonymizer.newVault();
  }

  /** Sessão com um cofre compartilhado por várias chamadas. */
  session(vault?: Vault): Session {
    return new Session(this, vault);
  }

  /** Outra instância com os mesmos detectores e outro operador. */
  withOperator(operator: string): Veu {
    const clone = Object.create(Veu.prototype) as Veu;
    Object.assign(clone, {
      options: { ...this.options, operator },
      analyzer: this.analyzer,
      anonymizer: new Anonymizer(this.analyzer, { ...this.options, operator }),
    });
    return clone;
  }
}

/** Um cofre compartilhado por várias chamadas: o mesmo CPF vira o mesmo [CPF_1] na conversa inteira. */
export class Session {
  readonly veu: Veu;
  readonly vault: Vault;
  private totals: Record<string, number> = {};

  constructor(veu: Veu = new Veu(), vault?: Vault) {
    this.veu = veu;
    this.vault = vault ?? veu.newVault();
  }

  anonymize(text: string): string {
    const result = this.veu.anonymize(text, this.vault);
    for (const [label, count] of Object.entries(result.counts())) this.totals[label] = (this.totals[label] ?? 0) + count;
    return result.text;
  }

  /** Anonimiza todos os textos de um objeto ou lista (por exemplo, uma lista de mensagens). */
  anonymizeData<T>(value: T): T {
    return mapStrings(value, (text) => this.anonymize(text)) as T;
  }

  restore(text: string): string {
    return this.vault.restore(text);
  }

  /** tool: os dados são argumentos de uma chamada de ferramenta (segue a política do cofre). */
  restoreData<T>(value: T, tool = false): T {
    return mapStrings(value, (text) => this.vault.restore(text, false, { tool })) as T;
  }

  restorer(): StreamRestorer {
    return this.vault.restorer();
  }

  /** Restaura um stream de pedaços de texto (por exemplo, a resposta de um modelo em streaming). */
  async *restoreStream(chunks: AsyncIterable<string> | Iterable<string>): AsyncGenerator<string> {
    const restorer = this.vault.restorer();
    for await (const chunk of chunks) {
      const ready = restorer.feed(chunk);
      if (ready) yield ready;
    }
    const tail = restorer.flush();
    if (tail) yield tail;
  }

  counts(): Record<string, number> {
    return { ...this.totals };
  }
}

export function mapStrings(value: unknown, transform: (text: string) => string): unknown {
  if (typeof value === "string") return transform(value);
  if (Array.isArray(value)) return value.map((item) => mapStrings(item, transform));
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, mapStrings(item, transform)]));
  }
  return value;
}

let defaultVeu: Veu | null = null;
const shared = (): Veu => (defaultVeu ??= new Veu());

/** Acha os dados pessoais e segredos de um texto. */
export function analyze(text: string): Entity[] {
  return shared().analyze(text);
}

/** Anonimiza um texto com a configuração padrão. */
export function anonymize(text: string, vault?: Vault): AnonymizationResult {
  return shared().anonymize(text, vault);
}

/** Restaura um texto com o cofre de uma anonimização anterior. */
export function restore(text: string, vault: Vault): string {
  return vault.restore(text);
}

/** Uma sessão com a configuração padrão. */
export function session(vault?: Vault): Session {
  return shared().session(vault);
}

/** Quantos dados de cada tipo há no texto (sem mostrar os valores). */
export function summarize(text: string): Record<string, number> {
  return counter(analyze(text).map((entity) => entity.label));
}
