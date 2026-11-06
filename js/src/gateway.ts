// Formatos das APIs de IA (equivalente a veu/gateway): onde estão os textos de cada requisição e resposta.
import type { Anonymizer } from "./anonymizer.ts";
import type { StreamRestorer, Vault } from "./vault.ts";

export const INSTRUCTION =
  "Alguns dados pessoais deste conteúdo foram trocados por marcadores entre colchetes, como [PESSOA_1] ou " +
  "[CPF_1]. Quando precisar se referir a esses dados, repita o marcador exatamente como está, inclusive os " +
  "colchetes. Não tente adivinhar nem completar os valores reais.";

// Blocos assinados ou criptografados pelo provedor: alterar o texto invalidaria a assinatura.
const UNTOUCHED_TYPES = new Set(["thinking", "redacted_thinking"]);
const UNTOUCHED_KEYS = new Set(["encrypted_content", "signature"]);

// deno-lint-ignore no-explicit-any
type Json = any;
export type Event = [name: string | null, data: Json];

const isObject = (value: unknown): value is Record<string, Json> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

/** Esconde os dados de todos os textos de uma requisição usando um único cofre. */
export class Masker {
  readonly anonymizer: Anonymizer;
  readonly vault: Vault;
  readonly counts: Record<string, number> = {};

  constructor(anonymizer: Anonymizer, vault: Vault) {
    this.anonymizer = anonymizer;
    this.vault = vault;
  }

  text(value: Json): Json {
    if (typeof value !== "string" || !value) return value;
    const result = this.anonymizer.anonymize(value, this.vault);
    for (const [label, count] of Object.entries(result.counts())) this.counts[label] = (this.counts[label] ?? 0) + count;
    return result.text;
  }

  /** Argumentos de ferramentas chegam como texto JSON: esconde os valores sem quebrar o JSON. */
  jsonString(value: Json): Json {
    if (typeof value !== "string" || !value) return value;
    try {
      return JSON.stringify(this.obj(JSON.parse(value)));
    } catch {
      return this.text(value);
    }
  }

  obj(value: Json): Json {
    if (typeof value === "string") return this.text(value);
    if (Array.isArray(value)) return value.map((item) => this.obj(item));
    if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([k, item]) => [k, this.obj(item)]));
    return value;
  }
}

export function restoreObj(value: Json, vault: Vault): Json {
  if (typeof value === "string") return vault.restore(value);
  if (Array.isArray(value)) return value.map((item) => restoreObj(item, vault));
  if (isObject(value)) {
    if (UNTOUCHED_TYPES.has(value.type)) return value;
    const restored: Record<string, Json> = {};
    for (const [key, item] of Object.entries(value)) {
      if (UNTOUCHED_KEYS.has(key)) restored[key] = item;
      else if ((key === "arguments" || key === "partial_json") && typeof item === "string") restored[key] = restoreJsonString(item, vault);
      else restored[key] = restoreObj(item, vault);
    }
    return restored;
  }
  return value;
}

export function restoreJsonString(value: string, vault: Vault): string {
  try {
    return JSON.stringify(restoreObj(JSON.parse(value), vault));
  } catch {
    return vault.restore(value, true);
  }
}

/** Um restaurador por campo de texto do stream (cada escolha, bloco ou argumento de ferramenta). */
export class StreamState {
  readonly vault: Vault;
  readonly meta: Record<string, Json> = {};
  private restorers = new Map<string, { key: Json[]; restorer: StreamRestorer }>();

  constructor(vault: Vault) {
    this.vault = vault;
  }

  feed(key: Json[], text: string, jsonEscape = false): string {
    const id = JSON.stringify(key);
    let entry = this.restorers.get(id);
    if (!entry) {
      entry = { key, restorer: this.vault.restorer(jsonEscape) };
      this.restorers.set(id, entry);
    }
    return entry.restorer.feed(text);
  }

  flush(key: Json[]): string {
    const id = JSON.stringify(key);
    const entry = this.restorers.get(id);
    this.restorers.delete(id);
    return entry ? entry.restorer.flush() : "";
  }

  pendingKeys(): Json[][] {
    return [...this.restorers.values()].filter((entry) => entry.restorer.pending).map((entry) => entry.key);
  }

  restore(value: Json): Json {
    return restoreObj(value, this.vault);
  }
}

export abstract class Adapter {
  abstract name: string;
  restoresOutput = true;
  abstract matches(method: string, path: string): boolean;
  abstract mask(payload: Json, masker: Masker): void;
  instruct(_payload: Json, _instruction: string): void {}
  isStream(payload: Json, _path: string): boolean {
    return payload.stream === true;
  }
  errorBody(message: string): Json {
    return { error: { message, type: "veu_bloqueado", code: "dados_pessoais_bloqueados" } };
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    return [[name, state.restore(data)]];
  }
  streamFinish(_state: StreamState): Event[] {
    return [];
  }
}

const trimSlash = (path: string): string => path.replace(/\/+$/, "");

function maskContent(content: Json, masker: Masker): Json {
  if (typeof content === "string") return masker.text(content);
  if (Array.isArray(content)) {
    for (const part of content) {
      if (isObject(part) && ["text", "input_text", "output_text"].includes(part.type)) part.text = masker.text(part.text);
    }
  }
  return content;
}

const template = (data: Json, keys: string[]): Json =>
  Object.fromEntries(keys.filter((key) => key in data).map((key) => [key, data[key]]));

export class OpenAIChatAdapter extends Adapter {
  name = "openai-chat";
  matches(method: string, path: string) {
    return method === "POST" && trimSlash(path).endsWith("/chat/completions");
  }
  mask(payload: Json, masker: Masker) {
    for (const message of payload.messages ?? []) {
      if (!isObject(message)) continue;
      message.content = maskContent(message.content, masker);
      for (const call of message.tool_calls ?? []) {
        if (isObject(call?.function)) call.function.arguments = masker.jsonString(call.function.arguments);
      }
      if (isObject(message.function_call)) message.function_call.arguments = masker.jsonString(message.function_call.arguments);
    }
  }
  instruct(payload: Json, instruction: string) {
    payload.messages ??= [];
    const first = payload.messages[0];
    if (isObject(first) && (first.role === "system" || first.role === "developer") && typeof first.content === "string") {
      first.content = `${first.content}\n\n${instruction}`;
    } else {
      payload.messages.unshift({ role: "system", content: instruction });
    }
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (data === "[DONE]") return [...this.streamFinish(state), [name, data]];
    if (!isObject(data)) return [[name, data]];
    state.meta.template = template(data, ["id", "object", "created", "model"]);
    for (const choice of data.choices ?? []) {
      const index = choice.index ?? 0;
      const delta = choice.delta;
      if (!isObject(delta)) continue;
      for (const field of ["content", "reasoning_content", "reasoning", "refusal"]) {
        if (typeof delta[field] === "string") delta[field] = state.feed(["c", index, field], delta[field]);
      }
      for (const call of delta.tool_calls ?? []) {
        if (typeof call?.function?.arguments === "string") {
          call.function.arguments = state.feed(["t", index, call.index ?? 0], call.function.arguments, true);
        }
      }
      if (choice.finish_reason) this.flushChoice(index, delta, state);
    }
    return [[name, data]];
  }
  private flushChoice(index: number, delta: Json, state: StreamState) {
    for (const key of state.pendingKeys()) {
      if (key[1] !== index) continue;
      const text = state.flush(key);
      if (!text) continue;
      if (key[0] === "c") {
        delta[key[2]] = (delta[key[2]] ?? "") + text;
      } else {
        delta.tool_calls ??= [];
        let call = delta.tool_calls.find((c: Json) => (c.index ?? 0) === key[2]);
        if (!call) {
          call = { index: key[2], function: { arguments: "" } };
          delta.tool_calls.push(call);
        }
        call.function ??= {};
        call.function.arguments = (call.function.arguments ?? "") + text;
      }
    }
  }
  streamFinish(state: StreamState): Event[] {
    const pending = state.pendingKeys();
    if (!pending.length) return [];
    const chunk: Json = { ...(state.meta.template ?? { object: "chat.completion.chunk" }) };
    const choices = new Map<number, Json>();
    for (const key of pending) if (!choices.has(key[1])) choices.set(key[1], { index: key[1], delta: {}, finish_reason: null });
    for (const [index, choice] of choices) this.flushChoice(index, choice.delta, state);
    chunk.choices = [...choices.values()];
    return [[null, chunk]];
  }
}

export class OpenAICompletionsAdapter extends Adapter {
  name = "openai-completions";
  matches(method: string, path: string) {
    const clean = trimSlash(path);
    return method === "POST" && clean.endsWith("/completions") && !clean.endsWith("/chat/completions");
  }
  mask(payload: Json, masker: Masker) {
    if (typeof payload.prompt === "string") payload.prompt = masker.text(payload.prompt);
    else if (Array.isArray(payload.prompt) && payload.prompt.every((p: Json) => typeof p === "string")) {
      payload.prompt = payload.prompt.map((p: string) => masker.text(p));
    }
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (data === "[DONE]") return [...this.streamFinish(state), [name, data]];
    if (!isObject(data)) return [[name, data]];
    state.meta.template = template(data, ["id", "object", "created", "model"]);
    for (const choice of data.choices ?? []) {
      const index = choice.index ?? 0;
      if (typeof choice.text === "string") choice.text = state.feed(["c", index], choice.text);
      if (choice.finish_reason) choice.text = (choice.text ?? "") + state.flush(["c", index]);
    }
    return [[name, data]];
  }
  streamFinish(state: StreamState): Event[] {
    const pending = state.pendingKeys();
    if (!pending.length) return [];
    const chunk: Json = { ...(state.meta.template ?? { object: "text_completion" }) };
    chunk.choices = pending.map((key) => ({ index: key[1], text: state.flush(key), finish_reason: null }));
    return [[null, chunk]];
  }
}

export class OpenAIEmbeddingsAdapter extends Adapter {
  name = "openai-embeddings";
  restoresOutput = false;
  matches(method: string, path: string) {
    return method === "POST" && trimSlash(path).endsWith("/embeddings");
  }
  mask(payload: Json, masker: Masker) {
    if (typeof payload.input === "string") payload.input = masker.text(payload.input);
    else if (Array.isArray(payload.input) && payload.input.every((p: Json) => typeof p === "string")) {
      payload.input = payload.input.map((p: string) => masker.text(p));
    }
  }
}

export class OpenAIResponsesAdapter extends Adapter {
  name = "openai-responses";
  matches(method: string, path: string) {
    return method === "POST" && trimSlash(path).endsWith("/responses");
  }
  mask(payload: Json, masker: Masker) {
    if (typeof payload.instructions === "string") payload.instructions = masker.text(payload.instructions);
    if (typeof payload.input === "string") {
      payload.input = masker.text(payload.input);
      return;
    }
    for (const item of payload.input ?? []) {
      if (!isObject(item) || item.type === "reasoning") continue;
      if ("content" in item) item.content = maskContent(item.content, masker);
      if (item.type === "function_call") item.arguments = masker.jsonString(item.arguments);
      else if (item.type === "function_call_output" && typeof item.output === "string") item.output = masker.text(item.output);
    }
  }
  instruct(payload: Json, instruction: string) {
    const current = payload.instructions;
    payload.instructions = typeof current === "string" && current ? `${current}\n\n${instruction}` : instruction;
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (!isObject(data)) return [[name, data]];
    const kind = data.type;
    if (kind === "response.output_text.delta") {
      data.delta = state.feed(["o", data.output_index ?? 0, data.content_index ?? 0], data.delta ?? "");
      return [[name, data]];
    }
    if (kind === "response.function_call_arguments.delta") {
      data.delta = state.feed(["f", data.output_index ?? 0], data.delta ?? "", true);
      return [[name, data]];
    }
    if (kind === "response.output_text.done" || kind === "response.function_call_arguments.done") {
      const text = kind === "response.output_text.done";
      const key = text ? ["o", data.output_index ?? 0, data.content_index ?? 0] : ["f", data.output_index ?? 0];
      const deltaKind = text ? "response.output_text.delta" : "response.function_call_arguments.delta";
      const events: Event[] = [];
      const tail = state.flush(key);
      if (tail) {
        const extra = template(data, ["item_id", "output_index", "content_index"]);
        events.push([name ? deltaKind : null, { type: deltaKind, ...extra, delta: tail }]);
      }
      events.push([name, state.restore(data)]);
      return events;
    }
    if (typeof kind === "string" && kind.includes("reasoning")) return [[name, data]];
    return [[name, state.restore(data)]];
  }
  streamFinish(state: StreamState): Event[] {
    const events: Event[] = [];
    for (const key of state.pendingKeys()) {
      const tail = state.flush(key);
      if (!tail) continue;
      if (key[0] === "o") {
        events.push([null, { type: "response.output_text.delta", output_index: key[1], content_index: key[2], delta: tail }]);
      } else {
        events.push([null, { type: "response.function_call_arguments.delta", output_index: key[1], delta: tail }]);
      }
    }
    return events;
  }
}

export class AnthropicMessagesAdapter extends Adapter {
  name = "anthropic-messages";
  matches(method: string, path: string) {
    const clean = trimSlash(path);
    return method === "POST" && (clean.endsWith("/messages") || clean.endsWith("/messages/count_tokens"));
  }
  private maskBlocks(blocks: Json, masker: Masker): Json {
    if (typeof blocks === "string") return masker.text(blocks);
    if (!Array.isArray(blocks)) return blocks;
    for (const block of blocks) {
      if (!isObject(block) || UNTOUCHED_TYPES.has(block.type)) continue;
      if (block.type === "text") block.text = masker.text(block.text);
      else if (block.type === "tool_use" || block.type === "server_tool_use") block.input = masker.obj(block.input);
      else if (block.type === "tool_result") block.content = this.maskBlocks(block.content, masker);
      else if (block.type === "document" && isObject(block.source)) {
        if (block.source.type === "text") block.source.data = masker.text(block.source.data);
        else if (block.source.type === "content") block.source.content = this.maskBlocks(block.source.content, masker);
      }
    }
    return blocks;
  }
  mask(payload: Json, masker: Masker) {
    if ("system" in payload) payload.system = this.maskBlocks(payload.system, masker);
    for (const message of payload.messages ?? []) if (isObject(message)) message.content = this.maskBlocks(message.content, masker);
  }
  instruct(payload: Json, instruction: string) {
    if (Array.isArray(payload.system)) payload.system.push({ type: "text", text: instruction });
    else if (typeof payload.system === "string" && payload.system) payload.system = `${payload.system}\n\n${instruction}`;
    else payload.system = instruction;
  }
  errorBody(message: string): Json {
    return { type: "error", error: { type: "invalid_request_error", message } };
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (!isObject(data)) return [[name, data]];
    const kind = data.type;
    if (kind === "content_block_start") return [[name, state.restore(data)]];
    if (kind === "content_block_delta") {
      const index = data.index ?? 0;
      const delta = data.delta ?? {};
      if (delta.type === "text_delta") delta.text = state.feed(["b", index, "text_delta"], delta.text ?? "");
      else if (delta.type === "input_json_delta") {
        delta.partial_json = state.feed(["b", index, "input_json_delta"], delta.partial_json ?? "", true);
      }
      return [[name, data]];
    }
    if (kind === "content_block_stop") return [...this.flushBlock(data.index ?? 0, state, name !== null), [name, data]];
    if (kind === "message_stop") {
      const events = state.pendingKeys().flatMap((key) => this.flushBlock(key[1], state, name !== null));
      return [...events, [name, data]];
    }
    return [[name, state.restore(data)]];
  }
  private flushBlock(index: number, state: StreamState, withNames: boolean): Event[] {
    const events: Event[] = [];
    for (const key of state.pendingKeys()) {
      if (key[1] !== index) continue;
      const tail = state.flush(key);
      if (!tail) continue;
      const field = key[2] === "text_delta" ? "text" : "partial_json";
      events.push([withNames ? "content_block_delta" : null, { type: "content_block_delta", index, delta: { type: key[2], [field]: tail } }]);
    }
    return events;
  }
  streamFinish(state: StreamState): Event[] {
    return state.pendingKeys().flatMap((key) => this.flushBlock(key[1], state, true));
  }
}

export class GeminiAdapter extends Adapter {
  name = "gemini";
  private methods = [":generateContent", ":streamGenerateContent", ":countTokens", ":embedContent", ":batchEmbedContents"];
  matches(method: string, path: string) {
    return method === "POST" && this.methods.some((suffix) => trimSlash(path).endsWith(suffix));
  }
  isStream(_payload: Json, path: string) {
    return path.includes(":streamGenerateContent");
  }
  private maskContent(content: Json, masker: Masker) {
    if (!isObject(content)) return;
    for (const part of content.parts ?? []) {
      if (!isObject(part) || part.thought) continue;
      if (typeof part.text === "string") part.text = masker.text(part.text);
      for (const key of ["functionCall", "function_call"]) if (isObject(part[key])) part[key].args = masker.obj(part[key].args);
      for (const key of ["functionResponse", "function_response"]) {
        if (isObject(part[key])) part[key].response = masker.obj(part[key].response);
      }
    }
  }
  mask(payload: Json, masker: Masker) {
    for (const content of payload.contents ?? []) this.maskContent(content, masker);
    for (const key of ["systemInstruction", "system_instruction", "content"]) this.maskContent(payload[key], masker);
    for (const request of payload.requests ?? []) if (isObject(request)) this.maskContent(request.content, masker);
    if (isObject(payload.generateContentRequest)) this.mask(payload.generateContentRequest, masker);
  }
  instruct(payload: Json, instruction: string) {
    if (!("contents" in payload)) return;
    const key = "system_instruction" in payload ? "system_instruction" : "systemInstruction";
    if (!isObject(payload[key])) payload[key] = { parts: [] };
    (payload[key].parts ??= []).push({ text: instruction });
  }
  errorBody(message: string): Json {
    return { error: { code: 400, message, status: "INVALID_ARGUMENT" } };
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (!isObject(data)) return [[name, data]];
    state.meta.template = template(data, ["modelVersion", "responseId"]);
    for (const candidate of data.candidates ?? []) {
      const index = candidate.index ?? 0;
      let lastText: Json = null;
      if (isObject(candidate.content)) {
        for (const part of candidate.content.parts ?? []) {
          if (!isObject(part) || part.thought) continue;
          if (typeof part.text === "string") {
            part.text = state.feed(["g", index], part.text);
            lastText = part;
          }
          for (const key of ["functionCall", "function_call"]) if (isObject(part[key])) part[key] = state.restore(part[key]);
        }
      }
      if (candidate.finishReason) {
        const tail = state.flush(["g", index]);
        if (tail) {
          if (lastText === null) {
            candidate.content ??= { role: "model", parts: [] };
            lastText = { text: "" };
            (candidate.content.parts ??= []).push(lastText);
          }
          lastText.text += tail;
        }
      }
    }
    return [[name, data]];
  }
  streamFinish(state: StreamState): Event[] {
    const pending = state.pendingKeys();
    if (!pending.length) return [];
    const chunk: Json = structuredClone(state.meta.template ?? {});
    chunk.candidates = pending.map((key) => ({ index: key[1], content: { role: "model", parts: [{ text: state.flush(key) }] } }));
    return [[null, chunk]];
  }
}

export class OllamaAdapter extends Adapter {
  name = "ollama";
  private paths = ["/api/chat", "/api/generate", "/api/embed", "/api/embeddings"];
  matches(method: string, path: string) {
    return method === "POST" && this.paths.some((suffix) => trimSlash(path).endsWith(suffix));
  }
  isStream(payload: Json, path: string) {
    const clean = trimSlash(path);
    return (clean.endsWith("/api/chat") || clean.endsWith("/api/generate")) && payload.stream !== false;
  }
  mask(payload: Json, masker: Masker) {
    for (const message of payload.messages ?? []) {
      if (!isObject(message)) continue;
      message.content = masker.text(message.content);
      for (const call of message.tool_calls ?? []) if (isObject(call?.function)) call.function.arguments = masker.obj(call.function.arguments);
    }
    for (const key of ["prompt", "system"]) if (typeof payload[key] === "string") payload[key] = masker.text(payload[key]);
    if (typeof payload.input === "string") payload.input = masker.text(payload.input);
    else if (Array.isArray(payload.input) && payload.input.every((p: Json) => typeof p === "string")) {
      payload.input = payload.input.map((p: string) => masker.text(p));
    }
  }
  instruct(payload: Json, instruction: string) {
    if ("messages" in payload) {
      const first = payload.messages[0];
      if (isObject(first) && first.role === "system") first.content = `${first.content ?? ""}\n\n${instruction}`;
      else payload.messages.unshift({ role: "system", content: instruction });
    } else if ("prompt" in payload) {
      payload.system = payload.system ? `${payload.system}\n\n${instruction}` : instruction;
    }
  }
  errorBody(message: string): Json {
    return { error: message };
  }
  streamEvent(name: string | null, data: Json, state: StreamState): Event[] {
    if (!isObject(data)) return [[name, data]];
    if (isObject(data.message)) {
      if (typeof data.message.content === "string") data.message.content = state.feed(["chat"], data.message.content);
      if (data.message.tool_calls) data.message.tool_calls = state.restore(data.message.tool_calls);
      if (data.done) data.message.content = (data.message.content ?? "") + state.flush(["chat"]);
    }
    if (typeof data.response === "string") {
      data.response = state.feed(["generate"], data.response);
      if (data.done) data.response += state.flush(["generate"]);
    }
    return [[name, data]];
  }
  streamFinish(state: StreamState): Event[] {
    return state.pendingKeys().map((key) => {
      const tail = state.flush(key);
      return key[0] === "chat"
        ? [null, { message: { role: "assistant", content: tail }, done: false }]
        : [null, { response: tail, done: false }];
    });
  }
}

export const ADAPTERS: Adapter[] = [
  new OpenAIChatAdapter(), new OpenAIResponsesAdapter(), new OpenAIEmbeddingsAdapter(), new OpenAICompletionsAdapter(),
  new AnthropicMessagesAdapter(), new GeminiAdapter(), new OllamaAdapter(),
];

export function detectAdapter(method: string, path: string): Adapter | null {
  const clean = path.split("?")[0];
  return ADAPTERS.find((adapter) => adapter.matches(method.toUpperCase(), clean)) ?? null;
}

export function encodeEvent(name: string | null, data: Json, extra: string[] = []): string {
  const lines = [...extra];
  if (name) lines.push(`event: ${name}`);
  const payload = typeof data === "string" ? data : JSON.stringify(data);
  for (const line of payload.split("\n")) lines.push(`data: ${line}`);
  return `${lines.join("\n")}\n\n`;
}

type Process = (name: string | null, data: Json) => Event[];
type Finish = () => Event[];

/** Recebe pedaços de um stream SSE e devolve o texto com os eventos transformados. */
export class SSETransformer {
  private decoder = new TextDecoder();
  private buffer = "";
  private pendingCR = false;
  private process: Process;
  private finish: Finish;

  constructor(process: Process, finish: Finish) {
    this.process = process;
    this.finish = finish;
  }

  feed(chunk: Uint8Array): string {
    let text = this.decoder.decode(chunk, { stream: true });
    if (this.pendingCR) {
      text = `\r${text}`;
      this.pendingCR = false;
    }
    if (text.endsWith("\r")) {
      text = text.slice(0, -1);
      this.pendingCR = true;
    }
    this.buffer += text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let output = "";
    for (let index = this.buffer.indexOf("\n\n"); index !== -1; index = this.buffer.indexOf("\n\n")) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      output += this.handle(block);
    }
    return output;
  }

  close(): string {
    this.buffer += this.decoder.decode().replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let output = this.buffer.trim() ? this.handle(this.buffer.replace(/^\n+|\n+$/g, "")) : "";
    this.buffer = "";
    for (const [name, data] of this.finish()) output += encodeEvent(name, data);
    return output;
  }

  private handle(block: string): string {
    let name: string | null = null;
    const dataLines: string[] = [];
    const extra: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":") || !line) {
        extra.push(line);
        continue;
      }
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") name = value;
      else if (field === "data") dataLines.push(value);
      else extra.push(line);
    }
    if (!dataLines.length) return `${block}\n\n`;
    const raw = dataLines.join("\n");
    let data: Json;
    try {
      data = JSON.parse(raw);
    } catch {
      data = raw;
    }
    const events = this.process(name, data);
    if (!events.length) return "";
    return events.map(([eventName, eventData], i) =>
      encodeEvent(eventName, eventData, i === events.length - 1 ? extra : [])).join("");
  }
}

/** O mesmo para streams de JSON por linha (API nativa do Ollama). */
export class NDJSONTransformer {
  private decoder = new TextDecoder();
  private buffer = "";
  private process: Process;
  private finish: Finish;

  constructor(process: Process, finish: Finish) {
    this.process = process;
    this.finish = finish;
  }

  feed(chunk: Uint8Array): string {
    this.buffer += this.decoder.decode(chunk, { stream: true });
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() ?? "";
    return lines.map((line) => this.handle(line)).join("");
  }

  close(): string {
    this.buffer += this.decoder.decode();
    let output = this.buffer.trim() ? this.handle(this.buffer) : "";
    this.buffer = "";
    for (const [, data] of this.finish()) output += NDJSONTransformer.encode(data);
    return output;
  }

  private static encode(data: Json): string {
    return `${typeof data === "string" ? data : JSON.stringify(data)}\n`;
  }

  private handle(raw: string): string {
    const line = raw.replace(/\r$/, "");
    if (!line.trim()) return `${line}\n`;
    let data: Json;
    try {
      data = JSON.parse(line);
    } catch {
      return `${line}\n`;
    }
    return this.process(null, data).map(([, eventData]) => NDJSONTransformer.encode(eventData)).join("");
  }
}

export function isStreaming(contentType: string): boolean {
  return contentType.includes("text/event-stream") || contentType.includes("ndjson");
}

export function streamTransformer(adapter: Adapter, vault: Vault, contentType: string): SSETransformer | NDJSONTransformer {
  const state = new StreamState(vault);
  const Transformer = contentType.includes("ndjson") ? NDJSONTransformer : SSETransformer;
  return new Transformer((name, data) => adapter.streamEvent(name, data, state), () => adapter.streamFinish(state));
}
