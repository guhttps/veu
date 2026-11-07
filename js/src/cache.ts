// Cache de detecção (equivalente a veu/cache.py): agentes reenviam a conversa inteira a cada turno.
// Guarda só posições, tipos e pontuações, nunca o texto; a chave é um HMAC-SHA256 com um sal aleatório.
// Só vale para textos longos. Num servidor com vários clientes, use uma instância do Veu por cliente.
import type { Candidate } from "./entities.ts";
import { hmacSha256, toHex } from "./sha256.ts";

export class DetectionCache {
  readonly maxEntries: number;
  readonly minChars: number;
  hits = 0;
  misses = 0;
  private readonly salt: Uint8Array;
  private readonly items = new Map<string, readonly Candidate[]>();
  private readonly encoder = new TextEncoder();

  constructor(maxEntries = 2048, minChars = 256) {
    this.maxEntries = maxEntries;
    this.minChars = minChars;
    const salt = new Uint8Array(32);
    globalThis.crypto.getRandomValues(salt);
    this.salt = salt;
  }

  usable(text: string): boolean {
    return this.maxEntries > 0 && text.length >= this.minChars;
  }

  private key(text: string, extra: string): string {
    return toHex(hmacSha256(this.salt, this.encoder.encode(`${extra}\u0000${text}`))).slice(0, 32);
  }

  get(text: string, extra = ""): readonly Candidate[] | undefined {
    const key = this.key(text, extra);
    const found = this.items.get(key);
    if (found === undefined) {
      this.misses += 1;
      return undefined;
    }
    this.items.delete(key);
    this.items.set(key, found);
    this.hits += 1;
    return found;
  }

  put(text: string, candidates: readonly Candidate[], extra = ""): void {
    const key = this.key(text, extra);
    this.items.delete(key);
    this.items.set(key, candidates.map((c) => ({ label: c.label, start: c.start, end: c.end, score: c.score, recognizer: c.recognizer })));
    while (this.items.size > this.maxEntries) this.items.delete(this.items.keys().next().value as string);
  }

  clear(): void {
    this.items.clear();
  }

  get size(): number {
    return this.items.size;
  }
}
