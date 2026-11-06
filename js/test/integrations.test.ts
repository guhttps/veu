// Integrações com os SDKs reais (OpenAI, Anthropic e AI SDK da Vercel), com um fetch falso no lugar da internet.
import assert from "node:assert/strict";
import { test } from "node:test";
import Anthropic from "@anthropic-ai/sdk";
import { generateText, streamText, wrapLanguageModel } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import OpenAI from "openai";
import { Veu } from "../src/index.ts";
import { veuMiddleware } from "../src/integrations/ai-sdk.ts";
import { createFetch } from "../src/integrations/fetch.ts";

const CPF = "529.982.247-25";
const PROMPT = `Cliente Maria Souza, CPF ${CPF}. Resuma.`;

function fakeServer(reply: (body: string, url: string) => Response) {
  const sent: string[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const body = await request.text();
    sent.push(body);
    return reply(body, request.url);
  };
  return { sent, fetch: fetch as typeof globalThis.fetch };
}

const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "content-type": "application/json" } });

function sse(events: string[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const event of events) controller.enqueue(encoder.encode(event));
      controller.close();
    },
  });
  return new Response(stream, { headers: { "content-type": "text/event-stream" } });
}

test("OpenAI SDK: chat sem streaming", async () => {
  const server = fakeServer(() => json({
    id: "c1", object: "chat.completion", created: 1, model: "m",
    choices: [{ index: 0, finish_reason: "stop", message: { role: "assistant", content: "Olá [PESSOA_1], CPF [CPF_1]." } }],
  }));
  const client = new OpenAI({ apiKey: "chave-de-teste", fetch: createFetch({ fetch: server.fetch }) });
  const reply = await client.chat.completions.create({ model: "m", messages: [{ role: "user", content: PROMPT }] });
  assert.ok(!server.sent[0].includes(CPF) && !server.sent[0].includes("Maria Souza"));
  assert.ok(server.sent[0].includes("[CPF_1]"));
  assert.equal(reply.choices[0].message.content, `Olá Maria Souza, CPF ${CPF}.`);
});

test("OpenAI SDK: streaming com marcador cortado entre eventos", async () => {
  const chunk = (content: string, finish: string | null = null) =>
    `data: ${JSON.stringify({ id: "c", object: "chat.completion.chunk", created: 1, model: "m", choices: [{ index: 0, delta: { content }, finish_reason: finish }] })}\n\n`;
  const server = fakeServer(() => sse([chunk("Olá [PES"), chunk("SOA_1], seu CPF é [CP"), chunk("F_1]", "stop"), "data: [DONE]\n\n"]));
  const client = new OpenAI({ apiKey: "chave-de-teste", fetch: createFetch({ fetch: server.fetch }) });
  const stream = await client.chat.completions.create({ model: "m", stream: true, messages: [{ role: "user", content: PROMPT }] });
  let text = "";
  for await (const part of stream) text += part.choices[0]?.delta?.content ?? "";
  assert.equal(text, `Olá Maria Souza, seu CPF é ${CPF}`);
});

test("Anthropic SDK: mensagens em streaming", async () => {
  const events = [
    ["message_start", { type: "message_start", message: { id: "m1", type: "message", role: "assistant", model: "m", content: [], stop_reason: null, usage: { input_tokens: 1, output_tokens: 1 } } }],
    ["content_block_start", { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } }],
    ["content_block_delta", { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "Oi [PESSOA" } }],
    ["content_block_delta", { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "_1]" } }],
    ["content_block_stop", { type: "content_block_stop", index: 0 }],
    ["message_delta", { type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 2 } }],
    ["message_stop", { type: "message_stop" }],
  ].map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
  const server = fakeServer(() => sse(events));
  const client = new Anthropic({ apiKey: "chave-de-teste", fetch: createFetch({ fetch: server.fetch }) });
  const stream = client.messages.stream({ model: "m", max_tokens: 50, messages: [{ role: "user", content: PROMPT }] });
  const message = await stream.finalMessage();
  assert.ok(!server.sent[0].includes(CPF));
  assert.equal(message.content[0].type === "text" ? message.content[0].text : "", "Oi Maria Souza");
});

test("fetch: bloqueia tipos proibidos sem enviar nada", async () => {
  const server = fakeServer(() => json({}));
  const client = new OpenAI({ apiKey: "chave-de-teste", maxRetries: 0, fetch: createFetch({ fetch: server.fetch, block: ["CPF"] }) });
  await assert.rejects(client.chat.completions.create({ model: "m", messages: [{ role: "user", content: PROMPT }] }), /bloqueada pelo Véu/);
  assert.equal(server.sent.length, 0);
});

test("fetch: requisições que não são de IA passam sem mudança", async () => {
  const server = fakeServer(() => new Response("ok"));
  const veuFetch = createFetch({ fetch: server.fetch });
  const response = await veuFetch("https://example.com/api/clientes", { method: "POST", body: `{"cpf":"${CPF}"}` });
  assert.equal(await response.text(), "ok");
  assert.equal(server.sent[0], `{"cpf":"${CPF}"}`);
});

test("fetch: Ollama com JSON por linha", async () => {
  const lines = [
    { message: { role: "assistant", content: "Oi [PES" }, done: false },
    { message: { role: "assistant", content: "SOA_1]" }, done: true },
  ].map((line) => `${JSON.stringify(line)}\n`);
  const server = fakeServer(() => {
    const response = sse(lines);
    return new Response(response.body, { headers: { "content-type": "application/x-ndjson" } });
  });
  const veuFetch = createFetch({ fetch: server.fetch });
  const response = await veuFetch("http://localhost:11434/api/chat", {
    method: "POST", body: JSON.stringify({ model: "m", messages: [{ role: "user", content: PROMPT }] }),
  });
  const text = (await response.text()).trim().split("\n").map((line) => JSON.parse(line).message.content).join("");
  assert.equal(text, "Oi Maria Souza");
});

test("AI SDK: generateText com middleware", async () => {
  let seen: unknown;
  const model = new MockLanguageModelV4({
    doGenerate: async (options) => {
      seen = options.prompt;
      return {
        content: [{ type: "text", text: "Olá [PESSOA_1], CPF [CPF_1]" }],
        finishReason: { unified: "stop", raw: "stop" },
        usage: { inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 }, outputTokens: { total: 1, text: 1, reasoning: 0 } },
        warnings: [],
      };
    },
  });
  const { text } = await generateText({ model: wrapLanguageModel({ model, middleware: veuMiddleware() }), prompt: PROMPT });
  assert.ok(!JSON.stringify(seen).includes(CPF));
  assert.equal(text, `Olá Maria Souza, CPF ${CPF}`);
});

test("AI SDK: streamText com marcador cortado", async () => {
  const parts = [
    { type: "stream-start", warnings: [] },
    { type: "text-start", id: "t" },
    { type: "text-delta", id: "t", delta: "Oi [PES" },
    { type: "text-delta", id: "t", delta: "SOA_1], CPF [CPF" },
    { type: "text-delta", id: "t", delta: "_1]" },
    { type: "text-end", id: "t" },
    { type: "finish", finishReason: { unified: "stop", raw: "stop" }, usage: { inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 }, outputTokens: { total: 1, text: 1, reasoning: 0 } } },
  ];
  const model = new MockLanguageModelV4({
    doStream: async () => ({ stream: new ReadableStream({ start(c) { for (const p of parts) c.enqueue(p as never); c.close(); } }) }),
  });
  const result = streamText({ model: wrapLanguageModel({ model, middleware: veuMiddleware({ veu: new Veu() }) }), prompt: PROMPT });
  let text = "";
  for await (const delta of result.textStream) text += delta;
  assert.equal(text, `Oi Maria Souza, CPF ${CPF}`);
});
