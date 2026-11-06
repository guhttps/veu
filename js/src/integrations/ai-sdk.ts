// Middleware para o AI SDK da Vercel: protege qualquer modelo (OpenAI, Anthropic, Google, Mistral...).
//
//   import { wrapLanguageModel, generateText } from "ai";
//   import { openai } from "@ai-sdk/openai";
//   import { veuMiddleware } from "veu-js/ai-sdk";
//
//   const model = wrapLanguageModel({ model: openai("gpt-5-mini"), middleware: veuMiddleware() });
//
// Esconde os dados do prompt (textos, argumentos e resultados de ferramentas) e restaura a resposta,
// inclusive em streaming. O raciocínio ("reasoning") não é alterado: ele pode vir assinado pelo provedor.
import { INSTRUCTION, Masker, restoreJsonString } from "../gateway.ts";
import { Session, Veu } from "../index.ts";
import type { StreamRestorer, Vault } from "../vault.ts";
import { BlockedError, type MaskInfo } from "./fetch.ts";

export { BlockedError } from "./fetch.ts";

// deno-lint-ignore no-explicit-any
type Json = any;

export interface VeuMiddlewareOptions {
  veu?: Veu;
  /** Sessão com um cofre compartilhado entre chamadas. */
  session?: Session;
  /** Tipos que fazem a chamada falhar com BlockedError em vez de serem escondidos. */
  block?: string[];
  /** Avisa o modelo para repetir os marcadores (padrão: true). */
  instructModel?: boolean;
  /** Versão da especificação de middleware: "v4" (AI SDK 7, padrão), "v3" (AI SDK 6) ou "v2" (AI SDK 5). */
  version?: "v2" | "v3" | "v4";
  onMask?: (info: MaskInfo) => void;
}

function maskToolOutput(output: Json, masker: Masker): Json {
  if (!output || typeof output !== "object") return output;
  if ((output.type === "text" || output.type === "error-text") && typeof output.value === "string") {
    return { ...output, value: masker.text(output.value) };
  }
  if (output.type === "json" || output.type === "error-json") return { ...output, value: masker.obj(output.value) };
  if (output.type === "content" && Array.isArray(output.value)) {
    return { ...output, value: output.value.map((item: Json) => (item?.type === "text" ? { ...item, text: masker.text(item.text) } : item)) };
  }
  return output;
}

function maskPart(part: Json, masker: Masker): Json {
  if (!part || typeof part !== "object") return part;
  switch (part.type) {
    case "text":
      return { ...part, text: masker.text(part.text) };
    case "tool-call":
      if ("input" in part) return { ...part, input: typeof part.input === "string" ? masker.jsonString(part.input) : masker.obj(part.input) };
      if ("args" in part) return { ...part, args: typeof part.args === "string" ? masker.jsonString(part.args) : masker.obj(part.args) };
      return part;
    case "tool-result":
      if ("output" in part) return { ...part, output: maskToolOutput(part.output, masker) };
      if ("result" in part) return { ...part, result: masker.obj(part.result) };
      return part;
    default:
      return part; // reasoning, arquivos e imagens não mudam
  }
}

export function maskPrompt(prompt: Json[], masker: Masker): Json[] {
  return prompt.map((message) => {
    if (message.role === "system") return { ...message, content: masker.text(message.content) };
    if (typeof message.content === "string") return { ...message, content: masker.text(message.content) };
    if (Array.isArray(message.content)) return { ...message, content: message.content.map((part: Json) => maskPart(part, masker)) };
    return message;
  });
}

function addInstruction(prompt: Json[]): Json[] {
  const first = prompt[0];
  if (first?.role === "system" && typeof first.content === "string") {
    return [{ ...first, content: `${first.content}\n\n${INSTRUCTION}` }, ...prompt.slice(1)];
  }
  return [{ role: "system", content: INSTRUCTION }, ...prompt];
}

function restoreContent(content: Json, vault: Vault): Json {
  if (!Array.isArray(content)) return content;
  return content.map((item) => {
    if (item?.type === "text" && typeof item.text === "string") return { ...item, text: vault.restore(item.text) };
    if (item?.type === "tool-call" && typeof item.input === "string") return { ...item, input: restoreJsonString(item.input, vault) };
    return item;
  });
}

export function veuMiddleware(options: VeuMiddlewareOptions = {}) {
  const veu = options.session?.veu ?? options.veu ?? new Veu();
  const block = new Set(options.block ?? veu.options.block ?? []);
  const instruct = options.instructModel ?? veu.options.instructModel ?? true;
  const vaults = new WeakMap<object, Vault>();
  const version = options.version ?? "v4";

  return {
    specificationVersion: version,
    ...(version === "v2" ? { middlewareVersion: "v2" as const } : {}),

    async transformParams({ params }: { params: Json; type?: string; model?: Json }) {
      const vault = options.session?.vault ?? veu.newVault();
      const masker = new Masker(veu.anonymizer, vault);
      let prompt = maskPrompt(params.prompt ?? [], masker);
      const labels = Object.keys(masker.counts);
      const blocked = labels.filter((label) => block.has(label)).sort();
      if (blocked.length) throw new BlockedError(blocked);
      if (instruct && labels.length && vault.hasPlaceholders) prompt = addInstruction(prompt);
      if (labels.length) options.onMask?.({ url: "ai-sdk", counts: { ...masker.counts } });
      const transformed = { ...params, prompt };
      vaults.set(transformed, vault);
      return transformed;
    },

    async wrapGenerate({ doGenerate, params }: { doGenerate: () => PromiseLike<Json>; params: Json }) {
      const result = await doGenerate();
      const vault = vaults.get(params);
      if (!vault?.size) return result;
      const restored = { ...result, content: restoreContent(result.content, vault) };
      if (typeof result.text === "string") restored.text = vault.restore(result.text);
      return restored;
    },

    async wrapStream({ doStream, params }: { doStream: () => PromiseLike<Json>; params: Json }) {
      const result = await doStream();
      const vault = vaults.get(params);
      if (!vault?.size) return result;
      return { ...result, stream: result.stream.pipeThrough(restoreStreamParts(vault)) };
    },
  };
}

/** Restaura as partes de um stream do AI SDK; um marcador cortado entre partes espera a próxima. */
export function restoreStreamParts(vault: Vault): TransformStream<Json, Json> {
  const restorers = new Map<string, { restorer: StreamRestorer; part: Json }>();
  const feed = (key: string, part: Json, text: string, json = false): string => {
    let entry = restorers.get(key);
    if (!entry) {
      entry = { restorer: vault.restorer(json), part };
      restorers.set(key, entry);
    }
    return entry.restorer.feed(text);
  };
  const flushKey = (key: string, controller: TransformStreamDefaultController<Json>) => {
    const entry = restorers.get(key);
    restorers.delete(key);
    const tail = entry?.restorer.flush();
    if (!entry || !tail) return;
    const { part } = entry;
    if ("textDelta" in part) controller.enqueue({ ...part, textDelta: tail });
    else controller.enqueue({ ...part, delta: tail });
  };
  const flushAll = (controller: TransformStreamDefaultController<Json>) => {
    for (const key of [...restorers.keys()]) flushKey(key, controller);
  };

  return new TransformStream({
    transform(part, controller) {
      switch (part?.type) {
        case "text-delta": {
          if (typeof part.delta === "string") {
            const key = `texto:${part.id ?? ""}`;
            controller.enqueue({ ...part, delta: feed(key, part, part.delta) });
          } else if (typeof part.textDelta === "string") {
            controller.enqueue({ ...part, textDelta: feed("texto", part, part.textDelta) });
          } else {
            controller.enqueue(part);
          }
          return;
        }
        case "tool-input-delta":
          controller.enqueue({ ...part, delta: feed(`ferramenta:${part.id ?? ""}`, part, part.delta ?? "", true) });
          return;
        case "text-end":
          flushKey(`texto:${part.id ?? ""}`, controller);
          controller.enqueue(part);
          return;
        case "tool-input-end":
          flushKey(`ferramenta:${part.id ?? ""}`, controller);
          controller.enqueue(part);
          return;
        case "tool-call":
          if (typeof part.input === "string") controller.enqueue({ ...part, input: restoreJsonString(part.input, vault) });
          else if (typeof part.args === "string") controller.enqueue({ ...part, args: restoreJsonString(part.args, vault) });
          else controller.enqueue(part);
          return;
        case "finish":
          flushAll(controller);
          controller.enqueue(part);
          return;
        default:
          controller.enqueue(part);
      }
    },
    flush(controller) {
      flushAll(controller);
    },
  });
}
