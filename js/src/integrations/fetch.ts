// fetch protegido: esconde os dados antes de a requisição sair e restaura a resposta, sem proxy.
//
//   import OpenAI from "openai";
//   import { createFetch } from "veu-js/fetch";
//   const client = new OpenAI({ fetch: createFetch() });
//
// Funciona com qualquer SDK ou código que aceite um fetch próprio (OpenAI, Anthropic, Ollama, APIs compatíveis).
import { INSTRUCTION, Masker, detectAdapter, isStreaming, restoreObj, streamTransformer } from "../gateway.ts";
import { Session, Veu } from "../index.ts";
import type { Vault } from "../vault.ts";

export interface MaskInfo {
  url: string;
  counts: Record<string, number>;
}

export interface CreateFetchOptions {
  /** Instância configurada do Véu (padrão: configuração padrão). */
  veu?: Veu;
  /** fetch usado de verdade (padrão: o fetch global). */
  fetch?: typeof globalThis.fetch;
  /** Sessão com um cofre compartilhado: o mesmo CPF vira o mesmo marcador em todas as chamadas. */
  session?: Session;
  /** Tipos que fazem a requisição ser recusada em vez de escondida (ex.: ["CHAVE_PRIVADA"]). */
  block?: string[];
  /** Avisa o modelo para repetir os marcadores (padrão: true). */
  instructModel?: boolean;
  /** Chamado a cada requisição com dados escondidos (só contagens, nunca os valores). */
  onMask?: (info: MaskInfo) => void;
}

export class BlockedError extends Error {
  readonly labels: string[];
  constructor(labels: string[]) {
    super(`Requisição bloqueada pelo Véu: contém dados que a política não permite enviar (${labels.join(", ")}).`);
    this.labels = labels;
  }
}

const DROP_RESPONSE_HEADERS = ["content-length", "content-encoding", "transfer-encoding"];

function responseHeaders(source: Headers): Headers {
  const headers = new Headers(source);
  for (const name of DROP_RESPONSE_HEADERS) headers.delete(name);
  return headers;
}

/** Cria um fetch que protege as chamadas a APIs de IA e repassa as outras sem mudar nada. */
export function createFetch(options: CreateFetchOptions = {}): typeof globalThis.fetch {
  const veu = options.session?.veu ?? options.veu ?? new Veu();
  const base = options.fetch ?? globalThis.fetch.bind(globalThis);
  const block = new Set(options.block ?? veu.options.block ?? []);
  const instruct = options.instructModel ?? veu.options.instructModel ?? true;

  return async function veuFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    // Decide pela URL e pelo método antes de tocar no corpo: criar um Request consumiria o corpo original.
    const rawUrl = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const adapter = detectAdapter(method, new URL(rawUrl, "http://localhost").pathname);
    if (!adapter) return base(input, init);
    const request = new Request(input, init);
    const url = new URL(request.url);
    const raw = await request.text();
    let payload: unknown;
    try {
      payload = JSON.parse(raw || "{}");
    } catch {
      return base(request.url, { method: request.method, headers: request.headers, body: raw, signal: request.signal });
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      return base(request.url, { method: request.method, headers: request.headers, body: raw, signal: request.signal });
    }
    const vault: Vault = options.session?.vault ?? veu.newVault();
    const masker = new Masker(veu.anonymizer, vault);
    adapter.mask(payload, masker);
    const blocked = Object.keys(masker.counts).filter((label) => block.has(label)).sort();
    if (blocked.length) {
      const message = new BlockedError(blocked).message;
      return new Response(JSON.stringify(adapter.errorBody(message)), {
        status: 400, headers: { "content-type": "application/json", "x-veu-bloqueado": blocked.join(",") },
      });
    }
    if (instruct && Object.keys(masker.counts).length && vault.hasPlaceholders) adapter.instruct(payload, INSTRUCTION);
    if (Object.keys(masker.counts).length) options.onMask?.({ url: `${url.origin}${url.pathname}`, counts: { ...masker.counts } });

    const headers = new Headers(request.headers);
    headers.delete("content-length");
    const response = await base(request.url, {
      method: request.method, headers, body: JSON.stringify(payload), signal: request.signal,
    });
    if (!adapter.restoresOutput || !vault.size || !response.body) return response;

    const contentType = response.headers.get("content-type") ?? "";
    if (isStreaming(contentType)) {
      const transformer = streamTransformer(adapter, vault, contentType);
      const encoder = new TextEncoder();
      const body = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          const output = transformer.feed(chunk);
          if (output) controller.enqueue(encoder.encode(output));
        },
        flush(controller) {
          const output = transformer.close();
          if (output) controller.enqueue(encoder.encode(output));
        },
      }));
      return new Response(body, { status: response.status, statusText: response.statusText, headers: responseHeaders(response.headers) });
    }
    const text = await response.text();
    let restored: string;
    try {
      restored = JSON.stringify(restoreObj(JSON.parse(text), vault));
    } catch {
      restored = vault.restore(text);
    }
    return new Response(restored, { status: response.status, statusText: response.statusText, headers: responseHeaders(response.headers) });
  };
}
