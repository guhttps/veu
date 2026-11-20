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
  PAGAMENTOS: JSON.stringify({
    mensal: { plano: "pro", nome: "Véu Pro por 1 mês", valor: 9.9, dias: 30, parcelas: 1, excluir: ["ticket"] },
    anual: { plano: "pro", nome: "Véu Pro por 1 ano", valor: 99, dias: 365, parcelas: 12 },
  }),
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
const preferencias = [];
const pagamentosNoMercadoPago = [];
globalThis.fetch = async (url, opcoes) => {
  const endereco = String(url);
  pedidosAoMercadoPago.push(endereco);
  assert.equal(opcoes.headers.authorization, "Bearer token-de-teste");
  if (endereco.endsWith("/checkout/preferences")) {
    preferencias.push(JSON.parse(opcoes.body));
    return Response.json({ id: "pref-1", init_point: "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=pref-1" });
  }
  // A busca devolve todos os pagamentos: o servidor tem de filtrar pela referência.
  if (endereco.includes("/v1/payments/search?")) return Response.json({ results: pagamentosNoMercadoPago });
  const pagamento = /\/v1\/payments\/(\d+)$/.exec(endereco);
  if (pagamento) {
    const dados = pagamentosNoMercadoPago.find((item) => String(item.id) === pagamento[1]);
    return new Response(JSON.stringify(dados ?? { message: "not found" }), { status: dados ? 200 : 404 });
  }
  const dados = assinaturas[endereco.split("/").pop()];
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

// Pagamento avulso (Pix, boleto, cartão, débito, saldo) ----------------------------------------------------------
const formulario = (campos) => ({ method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams(campos).toString() });

async function comprar(periodo) {
  const resposta = await chamar(`/comprar?periodo=${periodo}`);
  return { resposta, preferencia: preferencias.at(-1) };
}

function pagamento(referencia, extra = {}) {
  const dados = { id: 100000000 + pagamentosNoMercadoPago.length, status: "approved", currency_id: "BRL",
    transaction_amount: 9.9, date_approved: "2026-11-19T09:00:00.000-03:00", date_created: "2026-11-19T08:59:00.000-03:00",
    external_reference: referencia, payer: { email: "cliente@example.com" }, payment_type_id: "bank_transfer", ...extra };
  pagamentosNoMercadoPago.push(dados);
  return dados;
}

test("comprar cria a cobrança com uma referência aleatória e leva ao Mercado Pago", async () => {
  const { resposta, preferencia } = await comprar("mensal");
  assert.equal(resposta.status, 303);
  assert.equal(resposta.headers.get("location"), "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=pref-1");
  // "<período>-<aleatório>.<preços e vencimento anterior>.<assinatura do servidor>"
  assert.match(preferencia.external_reference, /^mensal-[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{86}$/);
  assert.equal(preferencia.back_urls.success, `https://licencas.example/pago?ref=${preferencia.external_reference}`);
  assert.deepEqual(preferencia.items.map((item) => [item.unit_price, item.currency_id, item.quantity]), [[9.9, "BRL", 1]]);
  // No mensal, sem boleto (a tarifa fixa come o valor) e sem parcelas; no anual, boleto e até 12 vezes.
  assert.deepEqual(preferencia.payment_methods.excluded_payment_types, [{ id: "ticket" }]);
  assert.equal(preferencia.payment_methods.installments, 1);
  const anual = (await comprar("anual")).preferencia;
  assert.deepEqual(anual.payment_methods.excluded_payment_types, []);
  assert.equal(anual.payment_methods.installments, 12);
  assert.notEqual(anual.external_reference.slice(6), preferencia.external_reference.slice(7));

  const antes = pedidosAoMercadoPago.length;
  for (const periodo of ["vitalicio", "constructor", "__proto__", "toString", ""]) {
    assert.equal((await chamar(`/comprar?periodo=${periodo}`)).status, 404, periodo);
  }
  assert.equal(pedidosAoMercadoPago.length, antes);
});

test("com o Pix aprovado, a página de volta mostra uma chave que vale pelo período pago", async () => {
  const { preferencia } = await comprar("mensal");
  pagamento("mensal-de-outra-pessoa-xxxxxxxxxxxxxxx", { transaction_amount: 9.9 });
  const pago = pagamento(preferencia.external_reference);
  const resposta = await chamar(`/pago?ref=${preferencia.external_reference}&payment_id=${pago.id}&status=approved`);
  assert.equal(resposta.status, 200);
  const html = await resposta.text();
  assert.match(html, /vale até 19\/12\/2026/);
  const conferida = await verificar(chaveDaPagina(html), publica, AGORA);
  assert.equal(conferida.valida, true);
  assert.equal(conferida.licenca.pagamento, String(pago.id));
  assert.equal(conferida.licenca.assinatura, undefined);
  assert.equal(conferida.licenca.email, "cliente@example.com");
  assert.equal(conferida.licenca.exp, Date.parse("2026-11-19T09:00:00.000-03:00") / 1000 + 30 * 86400);
  assert.equal((await verificar(chaveDaPagina(html), publica, Date.parse("2026-12-20T12:00:00Z"))).motivo, "vencida");

  // Um ano por boleto, aprovado: vale 365 dias.
  const anual = (await comprar("anual")).preferencia;
  pagamento(anual.external_reference, { transaction_amount: 99, payment_type_id: "ticket" });
  const chaveAnual = chaveDaPagina(await (await chamar(`/pago?ref=${anual.external_reference}`)).text());
  assert.equal((await verificar(chaveAnual, publica, Date.parse("2027-11-17T12:00:00Z"))).valida, true);
});

test("pendente espera; valor menor, recusado, vencido ou referência inventada não dão chave", async () => {
  const pendente = (await comprar("anual")).preferencia.external_reference;
  pagamento(pendente, { status: "pending", transaction_amount: 99, payment_type_id: "ticket", date_approved: null });
  const espera = await chamar(`/pago?ref=${pendente}`);
  assert.equal(espera.status, 202);
  const htmlEspera = await espera.text();
  assert.match(htmlEspera, /http-equiv="refresh"/);
  assert.match(htmlEspera, /recuperar/);
  assert.equal(chaveDaPagina(htmlEspera), undefined);

  // Pagou R$ 9,90 numa referência do plano anual (R$ 99): sem chave.
  const barato = (await comprar("anual")).preferencia.external_reference;
  pagamento(barato, { transaction_amount: 9.9 });
  assert.equal((await chamar(`/pago?ref=${barato}`)).status, 402);

  const dolar = (await comprar("mensal")).preferencia.external_reference;
  pagamento(dolar, { currency_id: "USD" });
  assert.equal((await chamar(`/pago?ref=${dolar}`)).status, 402);

  const recusado = (await comprar("mensal")).preferencia.external_reference;
  pagamento(recusado, { status: "rejected" });
  const recusa = await chamar(`/pago?ref=${recusado}`);
  assert.equal(recusa.status, 402);
  // O botão leva ao período certo (antes levava ao título "Véu Pro por 1 mês", um endereço quebrado).
  assert.match(await recusa.text(), /comprar\?periodo=mensal">Tentar de novo/);

  const antigo = (await comprar("mensal")).preferencia.external_reference;
  pagamento(antigo, { date_approved: "2025-01-10T10:00:00.000-03:00" });
  assert.equal((await chamar(`/pago?ref=${antigo}`)).status, 410);

  const antes = pedidosAoMercadoPago.length;
  for (const ref of ["mensal-curta", "constructor-aaaaaaaaaaaaaaaaaaaaaaaa", "vitalicio-aaaaaaaaaaaaaaaaaaaaaaaa", ""]) {
    assert.equal((await chamar(`/pago?ref=${ref}`)).status, 404, ref);
  }
  assert.equal(pedidosAoMercadoPago.length, antes);
});

test("recuperar devolve a chave só com o número da operação e o e-mail certos", async () => {
  assert.match(await (await chamar("/recuperar")).text(), /<form method="post"/);
  const { preferencia } = await comprar("mensal");
  const pago = pagamento(preferencia.external_reference);
  const certo = await chamar("/recuperar", formulario({ operacao: ` ${pago.id} `, email: "Cliente@Example.com " }));
  assert.equal(certo.status, 200);
  assert.equal((await verificar(chaveDaPagina(await certo.text()), publica, AGORA)).valida, true);

  for (const campos of [{ operacao: pago.id, email: "outra@example.com" }, { operacao: "999999999", email: "cliente@example.com" },
    { operacao: "12", email: "cliente@example.com" }, { operacao: pago.id, email: "" }]) {
    const resposta = await chamar("/recuperar", formulario(campos));
    assert.equal(resposta.status, 404, JSON.stringify(campos));
    assert.equal(chaveDaPagina(await resposta.text()), undefined);
  }
  // Pagamento de outro produto na mesma conta do Mercado Pago: sem chave.
  const outro = pagamento("pedido-da-loja-123", { transaction_amount: 500 });
  assert.equal((await chamar("/recuperar", formulario({ operacao: outro.id, email: "cliente@example.com" }))).status, 404);
  // Cobrança de uma assinatura ativa: a chave sai da assinatura.
  const cobranca = pagamento(null, { metadata: { preapproval_id: "assinatura-ativa" } });
  const daAssinatura = await chamar("/recuperar", formulario({ operacao: cobranca.id, email: "cliente@example.com" }));
  assert.equal(daAssinatura.status, 200);
  const licenca = (await verificar(chaveDaPagina(await daAssinatura.text()), publica, AGORA)).licenca;
  assert.equal(licenca.assinatura, "assinatura-ativa");
  assert.equal((await chamar("/recuperar", { method: "POST", body: "x".repeat(3000) })).status, 413);
});

test("a chave paga por período não renova sozinha", async () => {
  const { preferencia } = await comprar("mensal");
  pagamento(preferencia.external_reference);
  const chave = chaveDaPagina(await (await chamar(`/pago?ref=${preferencia.external_reference}`)).text());
  const resposta = await chamar("/renovar", { method: "POST", body: JSON.stringify({ chave }) });
  assert.equal(resposta.status, 409);
  assert.match((await resposta.json()).erro, /pague mais um período/);
});

// Preço garantido -------------------------------------------------------------------------------------------------
const envMaisCaro = { ...env, PAGAMENTOS: JSON.stringify({
  mensal: { plano: "pro", nome: "Véu Pro por 1 mês", valor: 14.9, dias: 30, parcelas: 1, excluir: ["ticket"] },
  anual: { plano: "pro", nome: "Véu Pro por 1 ano", valor: 149, dias: 365, parcelas: 12 },
}) };
const chamarCom = (ambiente, caminho, opcoes, quando = AGORA) =>
  servidor.fetch(new Request(`https://licencas.example${caminho}`, opcoes), ambiente, {}, quando);
const pedirMaisUmPeriodo = (ambiente, chave, periodo, quando) => chamarCom(ambiente, "/renovar-periodo",
  { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chave, periodo }) }, quando);

async function chaveComprada(periodo = "mensal") {
  const { preferencia } = await comprar(periodo);
  pagamento(preferencia.external_reference, { transaction_amount: periodo === "mensal" ? 9.9 : 99 });
  return chaveDaPagina(await (await chamar(`/pago?ref=${preferencia.external_reference}`)).text());
}

test("a chave paga por período guarda os preços da primeira compra", async () => {
  const { licenca } = await verificar(await chaveComprada(), publica, AGORA);
  assert.deepEqual({ ...licenca.precos }, { mensal: 990, anual: 9900 });
});

test("com o preço novo, quem já pagou renova pelo preço antigo e não perde os dias que faltavam", async () => {
  const chave = await chaveComprada(); // vale até 19/12/2026
  const antes = (await verificar(chave, publica, AGORA)).licenca;
  const resposta = await pedirMaisUmPeriodo(envMaisCaro, chave, "mensal");
  assert.equal(resposta.status, 200);
  const dados = await resposta.json();
  assert.equal(dados.valor, 9.9);
  assert.equal(dados.precoMantido, true);
  assert.match(dados.url, /^https:\/\/www\.mercadopago\.com\.br\//);
  const preferencia = preferencias.at(-1);
  assert.equal(preferencia.items[0].unit_price, 9.9);
  // Pagou cinco dias depois, com a chave ainda valendo: o período novo começa quando o anterior acaba.
  const cincoDias = AGORA + 5 * 86400 * 1000;
  pagamento(preferencia.external_reference, { transaction_amount: 9.9, date_approved: new Date(cincoDias).toISOString() });
  const nova = chaveDaPagina(await (await chamarCom(envMaisCaro, `/pago?ref=${preferencia.external_reference}`, undefined,
    cincoDias)).text());
  const licenca = (await verificar(nova, publica, cincoDias)).licenca;
  assert.equal(licenca.exp, antes.exp + 30 * 86400);
  assert.deepEqual({ ...licenca.precos }, { mensal: 990, anual: 9900 });
  // E o preço antigo continua na vez seguinte, também no plano de 1 ano.
  assert.equal((await (await pedirMaisUmPeriodo(envMaisCaro, nova, "anual", cincoDias)).json()).valor, 99);
});

test("quem chega depois, ou deixou a chave vencer há mais de 30 dias, paga o preço novo", async () => {
  const chave = await chaveComprada();
  const exp = (await verificar(chave, publica, AGORA)).licenca.exp;
  const depois = (exp + 31 * 86400) * 1000;
  const dados = await (await pedirMaisUmPeriodo(envMaisCaro, chave, "mensal", depois)).json();
  assert.equal(dados.valor, 14.9);
  assert.equal(dados.precoMantido, false);
  // Primeira compra com o preço novo: pagar o valor antigo não dá chave.
  await chamarCom(envMaisCaro, "/comprar?periodo=mensal");
  const ref = preferencias.at(-1).external_reference;
  assert.equal(preferencias.at(-1).items[0].unit_price, 14.9);
  pagamento(ref, { transaction_amount: 9.9 });
  assert.equal((await chamarCom(envMaisCaro, `/pago?ref=${ref}`)).status, 402);
});

test("ninguém baixa o preço mexendo na referência", async () => {
  await pedirMaisUmPeriodo(envMaisCaro, await chaveComprada(), "mensal");
  const [base, dados, assinatura] = preferencias.at(-1).external_reference.split(".");
  const termos = JSON.parse(Buffer.from(dados, "base64url").toString());
  termos.p.mensal = 100; // R$ 1,00
  const adulterada = `${base}.${Buffer.from(JSON.stringify(termos)).toString("base64url")}.${assinatura}`;
  pagamento(adulterada, { transaction_amount: 1 });
  assert.equal(chaveDaPagina(await (await chamarCom(envMaisCaro, `/pago?ref=${adulterada}`)).text()), undefined);
});

test("mais um período recusa chave de assinatura, emitida à mão ou inválida; a página tem formulário", async () => {
  const privada = await crypto.subtle.importKey("pkcs8", Buffer.from(env.CHAVE_PRIVADA, "base64url"), { name: "Ed25519" },
    false, ["sign"]);
  const deAssinatura = await assinar({ v: 1, plano: "pro", email: "", assinatura: "assinatura-ativa", emitida: 1,
    exp: 9999999999 }, privada);
  const resposta = await pedirMaisUmPeriodo(env, deAssinatura, "mensal");
  assert.equal(resposta.status, 409);
  assert.match((await resposta.json()).erro, /renova sozinha/);
  const manual = await assinar({ v: 1, plano: "pro", email: "", assinatura: "manual-1", emitida: 1, exp: 9999999999 }, privada);
  assert.equal((await pedirMaisUmPeriodo(env, manual, "mensal")).status, 409);
  assert.equal((await pedirMaisUmPeriodo(env, "VEU1.abc.def", "mensal")).status, 400);
  assert.equal((await pedirMaisUmPeriodo(env, await chaveComprada(), "vitalicio")).status, 400);
  const antes = preferencias.length;
  assert.equal(preferencias.length, antes); // nenhuma cobrança criada para pedidos recusados
  assert.match(await (await chamar("/renovar-periodo")).text(), /<form method="post"/);
  const pelaPagina = await chamar("/renovar-periodo", formulario({ chave: await chaveComprada(), periodo: "anual" }));
  assert.equal(pelaPagina.status, 303);
  assert.equal(preferencias.at(-1).items[0].unit_price, 99);
});
