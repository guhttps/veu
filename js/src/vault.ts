// Cofre: mapeamento entre marcadores e dados reais, e restauração (equivalente a veu/vault.py).
import { hmacSha256, toHex } from "./sha256.ts";
import { fold, onlyDigits } from "./text.ts";

/** Rótulos comparados só pelos dígitos ("529.982.247-25" e "52998224725" são o mesmo CPF). */
export const DIGIT_LABELS: ReadonlySet<string> = new Set([
  "CPF", "TELEFONE", "CEP", "CARTAO_CREDITO", "PIS", "CNS", "CNH", "TITULO_ELEITOR", "RENAVAM",
  "CONTA_BANCARIA", "PROCESSO",
]);
export const CODE_LABELS: ReadonlySet<string> = new Set(["CNPJ", "RG", "PLACA", "PASSAPORTE", "CHAVE_PIX"]);

// O colchete final é opcional: modelos às vezes escrevem "[CPF_1" ou "[CPF 1]".
const PLACEHOLDER = "\\[\\s*(?<ph_label>[A-Za-z]+(?:_[A-Za-z]+)*)[_\\s-]+(?<ph_id>[0-9A-Fa-f]{1,8})(?:\\s*\\]|(?![\\p{L}\\p{N}_]))";
const BARE = "(?<![\\p{L}\\p{N}_\\[])(?<bare_label>[A-Z]+(?:_[A-Z]+)*)_(?<bare_id>\\d{1,6}|[0-9a-f]{8})(?![\\p{L}\\p{N}_\\]])";
const RESTORE = new RegExp(`${PLACEHOLDER}|${BARE}`, "gu");
const TRAILING_WORD = /^[A-Za-z0-9_]+$/;
export const MAX_HOLDBACK = 48;

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

  constructor(secret?: Uint8Array | string) {
    this.secret = typeof secret === "string" ? new TextEncoder().encode(secret) : secret ?? randomSecret();
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
      const digest = toHex(hmacSha256(this.secret, new TextEncoder().encode(`${label}:${normalized}`)));
      replacement = `[${label}_${digest.slice(0, 8)}]`;
    } else {
      const next = (this.counters.get(label) ?? 0) + 1;
      this.counters.set(label, next);
      replacement = `[${label}_${next}]`;
    }
    this.store(key, { label, original: value, replacement, kind: "marcador" });
    return replacement;
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

  /** Troca os marcadores pelos valores reais. jsonEscape: o texto é um pedaço de JSON. */
  restore(text: string, jsonEscape = false): string {
    if (!text || !this.items.size) return text;
    return text.replace(RESTORE, (...args) => {
      const groups = args[args.length - 1] as Record<string, string | undefined>;
      const match = args[0] as string;
      let key: string;
      if (groups.ph_label) key = `[${groups.ph_label.toUpperCase()}_${groups.ph_id!.toLowerCase()}]`;
      else key = `[${groups.bare_label}_${groups.bare_id}]`;
      const entry = this.items.get(key);
      if (!entry || entry.kind !== "marcador") return match;
      return jsonEscape ? JSON.stringify(entry.original).slice(1, -1) : entry.original;
    });
  }

  restorer(jsonEscape = false): StreamRestorer {
    return new StreamRestorer(this, jsonEscape);
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

  static fromJSON(data: VaultData, secret?: Uint8Array | string): Vault {
    const vault = new Vault(secret);
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
  readonly vault: Vault;
  readonly jsonEscape: boolean;

  constructor(vault: Vault, jsonEscape = false) {
    this.vault = vault;
    this.jsonEscape = jsonEscape;
  }

  feed(text: string): string {
    if (!text) return "";
    this.buffer += text;
    const cut = this.safeCut(this.buffer);
    const ready = this.buffer.slice(0, cut);
    this.buffer = this.buffer.slice(cut);
    return this.vault.restore(ready, this.jsonEscape);
  }

  flush(): string {
    const ready = this.buffer;
    this.buffer = "";
    return this.vault.restore(ready, this.jsonEscape);
  }

  get pending(): boolean {
    return this.buffer.length > 0;
  }

  private safeCut(text: string): number {
    let cut = text.length;
    const bracket = text.lastIndexOf("[");
    if (bracket !== -1 && !text.slice(bracket).includes("]") && text.length - bracket <= MAX_HOLDBACK) cut = bracket;
    const longest = Math.min(text.length, MAX_HOLDBACK);
    const alnum = /[\p{L}\p{N}]/u;
    for (let size = longest; size > 0; size -= 1) {
      const start = text.length - size;
      if (start >= cut) break;
      if (start > 0 && alnum.test(text[start - 1]) && alnum.test(text[start])) continue;
      if (this.vault.mightContinue(text.slice(start))) {
        cut = start;
        break;
      }
    }
    return cut;
  }
}
