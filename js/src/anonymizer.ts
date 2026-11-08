// Troca os dados encontrados por marcadores ou máscaras (equivalente a veu/anonymizer.py).
import type { Analyzer } from "./analyzer.ts";
import { SECRET_LABELS, type Entity } from "./entities.ts";
import { CONNECTORS, ambiguousNames, capitalizedOnlyNames } from "./persons.ts";
import { secretPrefix } from "./secrets.ts";
import { parseDate } from "./validators.ts";
import { bisectRight, counter, escapeRegex, fold } from "./text.ts";
import { Vault, neutralizePlaceholders, type RestorePolicy } from "./vault.ts";

export const OPERATORS: Record<string, string> = {
  token: "marcador reversível, como [CPF_1] (padrão)",
  mascara: "mascara parte do valor, como ***.982.247-**; não é reversível",
  remover: "troca pelo tipo, como [CPF]; não é reversível",
  hash: "marcador estável entre requisições, como [CPF_3fa2c1d9]; reversível com o mesmo cofre",
  generalizar: "guarda só o que serve para análise (ano de nascimento, região do CEP, DDD, rede do IP) e troca o resto pelo tipo; não é reversível",
};
const ALIASES: Record<string, string> = {
  marcador: "token", "máscara": "mascara", mask: "mascara", redact: "remover", generalize: "generalizar",
};

/** Versão menos precisa do valor, que ainda serve para análises (idade, região) e identifica menos. */
export function generalizeValue(label: string, value: string): string {
  const digits = value.replace(/\D/g, "");
  if (label === "DATA_NASCIMENTO") {
    const parsed = parseDate(value);
    if (parsed) return String(parsed.getUTCFullYear());
  } else if (label === "CEP" && digits.length === 8) {
    return `${digits.slice(0, 5)}-***`;
  } else if (label === "TELEFONE") {
    const country = /^\s*\+(\d{1,3})/.exec(value);
    if (country && country[1] !== "55") return `+${country[1]} ****`;
    const local = (digits.length === 12 || digits.length === 13) && digits.startsWith("55") ? digits.slice(2) : digits;
    if (local.length === 10 || local.length === 11) return `(${local.slice(0, 2)}) ****-****`;
  } else if (label === "IP") {
    if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(value)) return `${value.split(".").slice(0, 3).join(".")}.0/24`;
    if (value.includes(":")) {
      const network = ipv6Network48(value);
      if (network) return network;
    }
  }
  return `[${label}]`;
}

/** Rede /48 de um IPv6, no formato do ipaddress do Python ("2001:db8:85a3::/48"). */
function ipv6Network48(value: string): string | null {
  const [head, tail = ""] = value.split("::");
  const left = head ? head.split(":") : [];
  const right = value.includes("::") ? (tail ? tail.split(":") : []) : [];
  if (!value.includes("::") && left.length !== 8) return null;
  const groups = [...left, ...Array(8 - left.length - right.length).fill("0"), ...right];
  if (groups.length !== 8 || groups.some((group) => !/^[0-9a-fA-F]{1,4}$/.test(group))) return null;
  const first = groups.slice(0, 3).map((group) => parseInt(group, 16).toString(16));
  while (first.length && first[first.length - 1] === "0") first.pop();
  return `${first.join(":")}::/48`;
}

export type Operator = "token" | "mascara" | "remover" | "hash" | "generalizar";

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
    const digit = /\p{Nd}/u; // inclui dígitos de largura total, como o isdigit() do Python
    const digits = [...value].filter((char) => digit.test(char));
    if (digits.length === 11) {
      let index = 0;
      return [...value].map((char) => {
        if (!digit.test(char)) return char;
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

// Palavras de nome (letras, com apóstrofo): a mesma definição do detector de nomes.
const NAME_WORD = /[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿ]+)*/gu;
const WORD_CHAR = /[\p{L}\p{N}_]/u;

/** Sequências de palavras cuja forma normalizada está em parts (a mais longa primeiro), com custo linear. */
function findNames(text: string, parts: Map<string, string>): [number, number][] {
  const longest = Math.max(...[...parts.keys()].map((key) => key.split(" ").length));
  const words = [...text.matchAll(NAME_WORD)].map((m) => [m.index, m.index + m[0].length, fold(m[0])] as const);
  const found: [number, number][] = [];
  let index = 0;
  while (index < words.length) {
    let matched = 0;
    for (let size = Math.min(longest, words.length - index); size > 0; size -= 1) {
      const chunk = words.slice(index, index + size);
      if (chunk.slice(1).some((word, i) => !/^\s+$/u.test(text.slice(chunk[i][1], word[0])))) continue;
      const start = chunk[0][0];
      const end = chunk[chunk.length - 1][1];
      if ((start > 0 && WORD_CHAR.test(text[start - 1])) || (end < text.length && WORD_CHAR.test(text[end]))) continue;
      if (parts.has(chunk.map((word) => word[2]).join(" "))) {
        found.push([start, end]);
        matched = size;
        break;
      }
    }
    index += matched || 1;
  }
  return found;
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
    if (operator === "generalizar") return generalizeValue(entity.label, entity.text);
    return `[${entity.label}]`;
  }

  /**
   * Propaga nomes já detectados no mesmo texto: menções soltas ao primeiro nome, ao sobrenome ou ao nome inteiro,
   * em qualquer caixa e com ou sem acento, recebem o mesmo marcador do nome completo. Nomes ambíguos não se propagam.
   */
  private linkPartialNames(text: string, entities: Entity[]): [Entity[], Map<number, string>] {
    const ambiguous = ambiguousNames();
    const capitalizedOnly = capitalizedOnlyNames();
    const parts = new Map<string, string>();
    // Nomes completos primeiro: "Ana" sozinho, antes de "Ana Beatriz Moura", usa o marcador do nome completo.
    const byLength = [...entities].sort((a, b) => b.text.split(/\s+/).length - a.text.split(/\s+/).length);
    for (const entity of byLength) {
      if (entity.label !== "PESSOA" || entity.score < 0.6) continue;
      const words = entity.text.split(/\s+/).filter((word) => word && !CONNECTORS.has(fold(word)));
      if (!words.length) continue;
      let linked: string[];
      if (words.length >= 2) {
        if (!parts.has(fold(entity.text))) parts.set(fold(entity.text), entity.text);
        linked = [words[0], words[words.length - 1]].filter((word) => word[0] !== word[0].toLowerCase());
      } else {
        linked = words;
      }
      for (const word of linked) {
        if ([...word].length >= 3 && !ambiguous.has(fold(word)) && !parts.has(fold(word))) parts.set(fold(word), entity.text);
      }
    }
    const canonical = new Map<number, string>();
    if (!parts.size) return [entities, canonical];
    const added: Entity[] = [];
    const starts = entities.map((e) => e.start);
    const ends = entities.map((e) => e.end);
    for (const [start, end] of findNames(text, parts)) {
      const position = bisectRight(starts, start);
      if (position > 0 && ends[position - 1] > start) continue;
      if (position < starts.length && starts[position] < end) continue;
      const key = fold(text.slice(start, end));
      // "Costa" é a pessoa; "costa" (o litoral) e "data de nascimento", não.
      if (capitalizedOnly.has(key) && text[start] === text[start].toLowerCase()) continue;
      added.push({ label: "PESSOA", start, end, score: 0.7, recognizer: "vinculo", text: text.slice(start, end) });
      canonical.set(start, parts.get(key)!);
    }
    for (const entity of entities) {
      const full = entity.label === "PESSOA" ? parts.get(fold(entity.text)) : undefined;
      if (full !== undefined && full !== entity.text) canonical.set(entity.start, full);
    }
    return [[...entities, ...added].sort((a, b) => a.start - b.start), canonical];
  }
}
