// Servidor de licenças e verificação da extensão juntos, com um Mercado Pago falso.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

import servidor, { abrir, assinar, paraBase64url } from "./worker.js";

const pares = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const publica = paraBase64url(await crypto.subtle.exportKey("raw", pares.publicKey));
const env = {
  CHAVE_PRIVADA: paraBase64url(await crypto.subtle.exportKey("pkcs8", pares.privateKey)),
  CHAVE_PUBLICA: publica,
  MP_TOKEN: "token-de-teste",
  PLANOS: JSON.stringify({ "plano-mensal": { plano: "pro", nome: "Pro mensal" } }),
};

// A verificação da extensão (extensao/licenca.js), carregada como no navegador.
const contexto = { crypto, TextEncoder, TextDecoder, atob, btoa, fetch: globalThis.fetch };
contexto.self = contexto;
vm.runInNewContext(readFileSync(new URL("../extensao/licenca.js", import.meta.url), "utf8"), contexto);
const { verificar } = contexto.veuLicenca;

const AGORA = Date.parse("2026-11-19T12:00:00Z");
const assinaturas = {
  "assinatura-ativa": { id: "assinatura-ativa", status: "authorized", preapproval_plan_id: "plano-mensal", payer_email: "cliente@example.com",
    next_payment_date: "2026-12-19T12:00:00.000-03:00" },
  "assinatura-pendente": { id: "assinatura-pendente", status: "pending", preapproval_plan_id: "plano-mensal" },
  "assinatura-outra": { id: "assinatura-outra", status: "authorized", preapproval_plan_id: "plano-de-outro-produto" },
  "assinatura-cancelada": { id: "assinatura-cancelada", status: "cancelled", preapproval_plan_id: "plano-mensal" },
};
const pedidosAoMercadoPago = [];
globalThis.fetch = async (url, opcoes) => {
  pedidosAoMercadoPago.push(String(url));
  assert.equal(opcoes.headers.authorization, "Bearer token-de-teste");
  const dados = assinaturas[String(url).split("/").pop()];
  return new Response(JSON.stringify(dados ?? { message: "not found" }), { status: dados ? 200 : 404 });
};

const chamar = (caminho, opcoes) => servidor.fetch(new Request(`https://licencas.example${caminho}`, opcoes), env, {}, AGORA);
const chaveDaPagina = (html) => /VEU1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/.exec(html)?.[0];

test("depois do pagamento, a página mostra uma chave que a extensão aceita", async () => {
  const resposta = await chamar("/pronto?preapproval_id=assinatura-ativa");
  assert.equal(resposta.status, 200);
  assert.match(resposta.headers.get("content-security-policy"), /default-src 'none'/);
  const chave = chaveDaPagina(await resposta.text());
  const conferida = await verificar(chave, publica, AGORA);
  assert.equal(conferida.valida, true);
  assert.equal(conferida.licenca.plano, "pro");
  assert.equal(conferida.licenca.email, "cliente@example.com");
  // Vale até a próxima cobrança mais 5 dias.
  assert.equal(conferida.licenca.exp, Date.parse("2026-12-19T12:00:00.000-03:00") / 1000 + 5 * 86400);
  assert.equal((await verificar(chave, publica, Date.parse("2026-12-25T12:00:00Z"))).motivo, "vencida");
});

test("sem pagamento confirmado, de outro produto ou com um id estranho, não há chave", async () => {
  for (const id of ["assinatura-pendente", "assinatura-outra", "assinatura-inexistente"]) {
    const resposta = await chamar(`/pronto?preapproval_id=${id}`);
    assert.equal(resposta.status, 402, id);
    assert.equal(chaveDaPagina(await resposta.text()), undefined);
  }
  const antes = pedidosAoMercadoPago.length;
  assert.equal((await chamar("/pronto?preapproval_id=..%2F..%2Fusers")).status, 402);
  assert.equal(pedidosAoMercadoPago.length, antes); // o id nem chega ao Mercado Pago
});

test("a renovação dá uma chave nova enquanto a assinatura estiver ativa", async () => {
  const privada = await crypto.subtle.importKey("pkcs8", Uint8Array.from(atob(env.CHAVE_PRIVADA.replace(/-/g, "+")
    .replace(/_/g, "/") + "=".repeat((4 - (env.CHAVE_PRIVADA.length % 4)) % 4)), (c) => c.charCodeAt(0)),
  { name: "Ed25519" }, false, ["sign"]);
  const velha = await assinar({ v: 1, plano: "pro", email: "cliente@example.com", assinatura: "assinatura-ativa", emitida: 1,
    exp: Math.floor(AGORA / 1000) - 86400 }, privada);
  const resposta = await chamar("/renovar", { method: "POST", body: JSON.stringify({ chave: velha }) });
  assert.equal(resposta.status, 200);
  assert.equal(resposta.headers.get("access-control-allow-origin"), "*");
  const { chave } = await resposta.json();
  assert.equal((await verificar(chave, publica, AGORA)).valida, true);

  const cancelada = await assinar({ v: 1, plano: "pro", email: "", assinatura: "assinatura-cancelada", emitida: 1, exp: 2 }, privada);
  const recusa = await chamar("/renovar", { method: "POST", body: JSON.stringify({ chave: cancelada }) });
  assert.equal(recusa.status, 402);
  assert.match((await recusa.json()).erro, /cancelled/);

  const manual = await assinar({ v: 1, plano: "empresa", email: "", assinatura: "manual-1", emitida: 1, exp: 2 }, privada);
  assert.equal((await chamar("/renovar", { method: "POST", body: JSON.stringify({ chave: manual }) })).status, 409);
});

test("chave adulterada, de outra chave privada ou fora do formato é recusada", async () => {
  const resposta = await chamar("/pronto?preapproval_id=assinatura-ativa");
  const chave = chaveDaPagina(await resposta.text());
  const [prefixo, dados, assinatura] = chave.split(".");
  const dadosFalsos = paraBase64url(new TextEncoder().encode(JSON.stringify({ ...JSON.parse(atob(dados.replace(/-/g, "+")
    .replace(/_/g, "/") + "=".repeat((4 - (dados.length % 4)) % 4))), plano: "empresa", exp: 9999999999 })));
  assert.equal((await verificar(`${prefixo}.${dadosFalsos}.${assinatura}`, publica, AGORA)).motivo, "assinatura");
  assert.equal((await verificar("VEU1.abc", publica, AGORA)).motivo, "formato");
  assert.equal((await verificar(chave, "", AGORA)).motivo, "sem-chave-publica");
  const outras = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const forjada = await assinar({ v: 1, plano: "pro", email: "", assinatura: "assinatura-ativa", emitida: 1, exp: 9999999999 },
    outras.privateKey);
  assert.equal((await verificar(forjada, publica, AGORA)).motivo, "assinatura");
  assert.equal(await abrir(forjada, await crypto.subtle.importKey("raw", Uint8Array.from(atob(publica.replace(/-/g, "+")
    .replace(/_/g, "/") + "="), (c) => c.charCodeAt(0)), { name: "Ed25519" }, false, ["verify"])), null);
  assert.equal((await chamar("/renovar", { method: "POST", body: JSON.stringify({ chave: forjada }) })).status, 400);
  assert.equal((await chamar("/renovar", { method: "POST", body: "{" })).status, 400);
});

test("CORS para a extensão e nada além das rotas conhecidas", async () => {
  assert.equal((await chamar("/renovar", { method: "OPTIONS" })).status, 204);
  assert.equal((await chamar("/admin")).status, 404);
  assert.equal((await chamar("/pronto", { method: "POST" })).status, 404);
});
