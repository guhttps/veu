// Troca os dados encontrados por marcadores ou máscaras (equivalente a veu/anonymizer.py).
import type { Analyzer } from "./analyzer.ts";
import { SECRET_LABELS, type Entity } from "./entities.ts";
import { CONNECTORS, ambiguousNames } from "./persons.ts";
import { secretPrefix } from "./secrets.ts";
import { bisectRight, counter, escapeRegex, fold } from "./text.ts";
import { Vault, neutralizePlaceholders, type RestorePolicy } from "./vault.ts";

export const OPERATORS: Record<string, string> = {
  token: "marcador reversível, como [CPF_1] (padrão)",
  mascara: "mascara parte do valor, como ***.982.247-**; não é reversível",
  remover: "troca pelo tipo, como [CPF]; não é reversível",
  hash: "marcador estável entre requisições, como [CPF_3fa2c1d9]; reversível com o mesmo cofre",
};
const ALIASES: Record<string, string> = { marcador: "token", "máscara": "mascara", mask: "mascara", redact: "remover" };

export type Operator = "token" | "mascara" | "remover" | "hash";

export function normalizeOperator(name: string): Operator {
  const key = name.trim().toLowerCase();
  const resolved = ALIASES[key] ?? key;
  if (resolved === "sintetico" || resolved === "sintético" || resolved === "synthetic") {
    throw new Error('O operador "sintetico" ainda não está disponível na versão JavaScript. Use token, mascara, remover ou hash.');
  }
  if (!(resolved in OPERATORS)) {
    throw new Error(`Operador desconhecido: "${name}". Use um destes: ${Object.keys(OPERATORS).join(", ")}.`);
  }
  return resolved as Operator;
}

export function maskValue(label: string, value: string): string {
  if (label === "CPF") {
    const digits = [...value].filter((char) => /\d/.test(char));
    if (digits.length === 11) {
      let index = 0;
      return [...value].map((char) => {
        if (!/\d/.test(char)) return char;
        const visible = index >= 3 && index < 9;
        index += 1;
        return visible ? char : "*";
      }).join("");
    }
  }
  if (label === "EMAIL" && value.includes("@")) {
    const at = value.lastIndexOf("@");
    return `${value.slice(0, 1)}***@${value.slice(at + 1)}`;
  }
  if (label === "PESSOA") {
    return value.split(/\s+/).filter(Boolean).map((word) => (CONNECTORS.has(fold(word)) ? word : `${word.slice(0, 1)}***`)).join(" ");
  }
  if (label === "SENHA" || label === "CHAVE_PRIVADA") return "********";
  if (label === "URL_CONEXAO" && value.includes("://")) return `${value.split("://")[0]}://****`;
  if (SECRET_LABELS.has(label)) return `${secretPrefix(value)}****`;
  const alnum = /[\p{L}\p{N}]/u;
  const positions = [...value].map((char, i) => (alnum.test(char) ? i : -1)).filter((i) => i >= 0);
  const keep = new Set(positions.length > 4 ? positions.slice(-2) : []);
  return [...value].map((char, i) => (!alnum.test(char) || keep.has(i) ? char : "*")).join("");
}

export interface Replacement {
  entity: Entity;
  replacement: string;
  operator: Operator;
}

export class AnonymizationResult {
  readonly text: string;
  readonly replacements: Replacement[];
  readonly vault: Vault;

  constructor(text: string, replacements: Replacement[], vault: Vault) {
    this.text = text;
    this.replacements = replacements;
    this.vault = vault;
  }

  get entities(): Entity[] {
    return this.replacements.map((item) => item.entity);
  }

  counts(): Record<string, number> {
    return counter(this.replacements.map((item) => item.entity.label));
  }

  /** Restaura um texto produzido a partir deste resultado (por exemplo, a resposta do modelo). */
  restore(text: string): string {
    return this.vault.restore(text);
  }
}

export interface AnonymizerOptions {
  operator?: string;
  operators?: Record<string, string>;
  linkNames?: boolean;
  secret?: Uint8Array | string;
  /** Onde a restauração pode devolver os dados reais (padrão: fora de links e sem segredos em ferramentas). */
  restore?: RestorePolicy;
}

export class Anonymizer {
  readonly analyzer: Analyzer;
  readonly operator: Operator;
  readonly operators: Record<string, Operator>;
  readonly linkNames: boolean;
  readonly secret?: Uint8Array | string;
  readonly restorePolicy: RestorePolicy;

  constructor(analyzer: Analyzer, options: AnonymizerOptions = {}) {
    this.analyzer = analyzer;
    this.operator = normalizeOperator(options.operator ?? "token");
    this.operators = Object.fromEntries(
      Object.entries(options.operators ?? {}).map(([label, op]) => [label.toUpperCase(), normalizeOperator(op)]),
    );
    this.linkNames = options.linkNames ?? true;
    this.secret = options.secret;
    this.restorePolicy = options.restore ?? {};
  }

  newVault(): Vault {
    return new Vault(this.secret, this.restorePolicy);
  }

  /**
   * neutralize (padrão true): desarma marcadores que já vêm no texto (`[CPF_1]` vira `[CPF#1]`), para que um
   * marcador escrito por outra pessoa nunca vire um dado real na restauração.
   */
  anonymize(text: string, vault: Vault = this.newVault(), neutralize = true): AnonymizationResult {
    if (neutralize) text = neutralizePlaceholders(text, vault.labels);
    let entities = this.analyzer.analyze(text);
    let canonical = new Map<number, string>();
    if (this.linkNames && entities.length) [entities, canonical] = this.linkPartialNames(text, entities);
    const output: string[] = [];
    const replacements: Replacement[] = [];
    let position = 0;
    for (const entity of entities) {
      const operator = this.operators[entity.label] ?? this.operator;
      const replacement = this.replace(entity, operator, vault, canonical.get(entity.start));
      output.push(text.slice(position, entity.start), replacement);
      replacements.push({ entity, replacement, operator });
      position = entity.end;
    }
    output.push(text.slice(position));
    return new AnonymizationResult(output.join(""), replacements, vault);
  }

  /** Substitui um valor inteiro já sabido ser de um tipo (ex.: toda a coluna "cpf" de uma planilha). */
  replaceValue(label: string, value: string, vault: Vault): string {
    const upper = label.toUpperCase();
    const entity: Entity = { label: upper, start: 0, end: value.length, score: 1, recognizer: "forcado", text: value };
    return this.replace(entity, this.operators[upper] ?? this.operator, vault, undefined);
  }

  private replace(entity: Entity, operator: Operator, vault: Vault, canonical: string | undefined): string {
    if (canonical !== undefined && (operator === "token" || operator === "hash")) {
      const replacement = this.replace({ ...entity, text: canonical }, operator, vault, undefined);
      vault.alias(entity.label, entity.text, replacement);
      return replacement;
    }
    if (operator === "token") return vault.placeholder(entity.label, entity.text);
    if (operator === "hash") return vault.placeholder(entity.label, entity.text, true);
    if (operator === "mascara") return maskValue(entity.label, entity.text);
    return `[${entity.label}]`;
  }

  /** Menções soltas ao primeiro nome ou ao sobrenome de uma pessoa já detectada usam o mesmo marcador. */
  private linkPartialNames(text: string, entities: Entity[]): [Entity[], Map<number, string>] {
    const ambiguous = ambiguousNames();
    const parts = new Map<string, string>();
    for (const entity of entities) {
      if (entity.label !== "PESSOA") continue;
      const words = entity.text.split(/\s+/).filter((word) => word && !CONNECTORS.has(fold(word)));
      if (words.length < 2) continue;
      for (const word of [words[0], words[words.length - 1]]) {
        if (word.length >= 3 && !ambiguous.has(fold(word)) && word[0] !== word[0].toLowerCase() && !parts.has(word)) {
          parts.set(word, entity.text);
        }
      }
    }
    const canonical = new Map<number, string>();
    if (!parts.size) return [entities, canonical];
    const alternatives = [...parts.keys()].sort((a, b) => b.length - a.length).map(escapeRegex).join("|");
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${alternatives})(?![\\p{L}\\p{N}_])`, "gu");
    const added: Entity[] = [];
    const starts = entities.map((e) => e.start);
    const ends = entities.map((e) => e.end);
    for (const match of text.matchAll(pattern)) {
      const start = match.index;
      const end = start + match[0].length;
      const position = bisectRight(starts, start);
      if (position > 0 && ends[position - 1] > start) continue;
      if (position < starts.length && starts[position] < end) continue;
      added.push({ label: "PESSOA", start, end, score: 0.7, recognizer: "vinculo", text: match[0] });
      canonical.set(start, parts.get(match[0])!);
    }
    const byFolded = new Map([...parts.entries()].map(([word, full]) => [fold(word), full]));
    for (const entity of entities) {
      if (entity.label === "PESSOA" && entity.text.split(/\s+/).filter(Boolean).length === 1 && byFolded.has(fold(entity.text))) {
        canonical.set(entity.start, byFolded.get(fold(entity.text))!);
      }
    }
    return [[...entities, ...added].sort((a, b) => a.start - b.start), canonical];
  }
}
