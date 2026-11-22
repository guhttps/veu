// Service worker da extensão (fundo.js + licenca.js) com uma API chrome falsa: preferências, licença e listas.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

import { assinar, paraBase64url } from "../../nuvem/worker.js";

const pasta = new URL("../", import.meta.url);
const pares = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const publica = paraBase64url(await crypto.subtle.exportKey("raw", pares.publicKey));
const agora = () => Math.floor(Date.now() / 1000);
const licenca = (dias, extra = {}) => assinar({ v: 1, plano: "pro", email: "cliente@example.com", assinatura: "assinatura-1",
  emitida: agora(), exp: agora() + dias * 86400, ...extra }, pares.privateKey);

function carregar({ politica = {} } = {}) {
  const store = { sync: {}, session: {}, local: {} };
  const area = (nome) => ({
    get: async (chaves) => {
      if (chaves === null) return { ...store[nome] };
      const lista = Array.isArray(chaves) ? chaves : [chaves];
      return Object.fromEntries(lista.filter((chave) => chave in store[nome]).map((chave) => [chave, store[nome][chave]]));
    },
    set: async (valores) => { Object.assign(store[nome], valores); },
    remove: async (chaves) => { for (const chave of [].concat(chaves)) delete store[nome][chave]; },
    setAccessLevel: () => {},
  });
  let receptor;
  const evento = () => ({ addListener: () => {} });
  const renovacoes = [];
  const abasAbertas = [];
  const pagamentosPedidos = [];
  const cancelamentos = [];
  const contexto = {
    console, crypto, TextEncoder, TextDecoder, atob, btoa,
    chrome: {
      storage: { managed: { get: async () => ({ ...politica }) }, sync: area("sync"), session: area("session"), local: area("local") },
      runtime: { onMessage: { addListener: (fn) => { receptor = fn; } }, onInstalled: evento(),
        getURL: (caminho) => `chrome-extension://veu/${caminho}` },
      tabs: { onRemoved: evento(), create: async (opcoes) => { abasAbertas.push(opcoes.url); } }, contextMenus: { onClicked: evento() },
      action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {} },
    },
  };
  contexto.globalThis = contexto;
  contexto.importScripts = (arquivo) => {
    vm.runInContext(readFileSync(new URL(arquivo, pasta), "utf8"), contexto);
    // A extensão de verdade traz a chave pública do Véu; aqui, a de teste. A renovação não sai para a rede.
    const { verificar } = contexto.veuLicenca;
    contexto.veuLicenca.verificar = (chave) => verificar(chave, publica);
    contexto.veuLicenca.renovar = async (chave) => { renovacoes.push(chave); return { chave: await licenca(30) }; };
    contexto.veuLicenca.cancelarAssinatura = async (chave) => { cancelamentos.push(chave); return { mensagem: "Assinatura cancelada." }; };
    contexto.veuLicenca.pagarPeriodo = async (chave, periodo) => {
      pagamentosPedidos.push({ chave, periodo });
      return periodo === "anual" ? { url: "https://golpe.example/pagar" }
        : { url: "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=1", valor: 9.9, precoMantido: true };
    };
  };
  vm.createContext(contexto);
  vm.runInContext(readFileSync(new URL("fundo.js", pasta), "utf8"), contexto);
  const enviar = (mensagem, remetente) => new Promise((resolver) => receptor(mensagem, remetente, resolver));
  return {
    store, renovacoes, abasAbertas, pagamentosPedidos, cancelamentos, contexto,
    doIcone: (mensagem) => enviar(mensagem, { id: "veu", url: "chrome-extension://veu/popup.html" }),
    daPagina: (mensagem) => enviar(mensagem, { tab: { id: 7 }, url: "https://chatgpt.com/" }),
  };
}

test("só o ícone muda as preferências, ativa a chave e salva as listas", async () => {
  const fundo = carregar();
  assert.match((await fundo.daPagina({ tipo: "salvarPreferencias", preferencias: { ativo: false } })).erro, /ícone/);
  assert.equal(fundo.store.sync.ativo, undefined);
  assert.match((await fundo.daPagina({ tipo: "ativarLicenca", chave: await licenca(30) })).erro, /ícone/);
  assert.match((await fundo.daPagina({ tipo: "salvarListas", listaNomes: ["Joana Prado"] })).erro, /ícone/);
  assert.equal((await fundo.doIcone({ tipo: "salvarPreferencias", preferencias: { ativo: false } })).ativo, false);
});

test("com a chave, o Pro liga e as listas ficam fora da sincronização", async () => {
  const fundo = carregar();
  assert.match((await fundo.doIcone({ tipo: "salvarListas", listaNomes: ["Joana Prado"] })).erro, /Véu Pro/);
  assert.match((await fundo.doIcone({ tipo: "ativarLicenca", chave: "qualquer coisa" })).erro, /VEU1/);
  const config = await fundo.doIcone({ tipo: "ativarLicenca", chave: await licenca(30) });
  assert.equal(config.pro.ativo, true);
  assert.equal(config.pro.email, "cliente@example.com");
  const salva = await fundo.doIcone({ tipo: "salvarListas", listaNomes: ["Joana Prado", " ", "x"], listaTermos: ["Projeto Netuno"] });
  assert.deepEqual([...salva.listaNomes], ["Joana Prado"]);
  assert.deepEqual([...fundo.store.local.listaTermos], ["Projeto Netuno"]);
  assert.equal(fundo.store.sync.listaNomes, undefined); // nomes de clientes não vão para a conta do navegador
  const removida = await fundo.doIcone({ tipo: "removerLicenca" });
  assert.equal(removida.pro.ativo, false);
});

test("chave de outra assinatura privada não liga o Pro", async () => {
  const fundo = carregar();
  const outras = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const forjada = await assinar({ v: 1, plano: "pro", email: "", assinatura: "x-123456", emitida: agora(),
    exp: agora() + 9e6 }, outras.privateKey);
  assert.match((await fundo.doIcone({ tipo: "ativarLicenca", chave: forjada })).erro, /não foi emitida/);
});

test("perto do vencimento, renova sozinho; longe, não", async () => {
  const fundo = carregar();
  await fundo.doIcone({ tipo: "ativarLicenca", chave: await licenca(30) });
  await fundo.doIcone({ tipo: "configuracao" });
  assert.equal(fundo.renovacoes.length, 0);
  fundo.store.local.licenca = await licenca(3);
  fundo.store.local.licencaTentativa = 0;
  await fundo.doIcone({ tipo: "configuracao" });
  await new Promise((resolver) => setTimeout(resolver, 50));
  assert.equal(fundo.renovacoes.length, 1);
  assert.equal((await fundo.doIcone({ tipo: "configuracao" })).pro.ativo, true);
  assert.equal(fundo.renovacoes.length, 1); // no máximo uma tentativa a cada 12 horas
});

test("a chave paga por período (Pix, boleto) não tenta renovar e avisa perto do fim", async () => {
  const fundo = carregar();
  const avulsa = (dias) => licenca(dias, { assinatura: undefined, pagamento: "123456789" });
  const config = await fundo.doIcone({ tipo: "ativarLicenca", chave: await avulsa(3) });
  await new Promise((resolver) => setTimeout(resolver, 50));
  assert.equal(config.pro.ativo, true);
  assert.equal(config.pro.avulsa, true);
  assert.equal(config.pro.acabando, true);
  assert.equal(fundo.renovacoes.length, 0); // nada vai para a rede
  // Vencida, nem é guardada: o período pago acabou.
  assert.match((await fundo.doIcone({ tipo: "ativarLicenca", chave: await avulsa(-1) })).erro, /pague mais um período/);
  assert.equal(fundo.renovacoes.length, 0);
  // A emitida à mão (cortesia, teste) também não renova.
  fundo.store.local.licenca = await licenca(2, { assinatura: "manual-1" });
  fundo.store.local.licencaTentativa = 0;
  assert.equal((await fundo.doIcone({ tipo: "configuracao" })).pro.avulsa, false);
  await new Promise((resolver) => setTimeout(resolver, 50));
  assert.equal(fundo.renovacoes.length, 0);
});

test("a chave e as listas da empresa vêm da política e não mudam pelo ícone", async () => {
  const fundo = carregar({ politica: { licenca: await licenca(365, { plano: "empresa", pessoas: 50 }), listaTermos: ["Netuno"] } });
  const config = await fundo.doIcone({ tipo: "configuracao" });
  assert.equal(config.pro.ativo, true);
  assert.equal(config.pro.daEmpresa, true);
  assert.deepEqual([...config.listaTermos], ["Netuno"]);
  const salva = await fundo.doIcone({ tipo: "salvarListas", listaNomes: ["Joana"], listaTermos: ["Outro"] });
  assert.deepEqual([...salva.listaTermos], ["Netuno"]);
  assert.deepEqual([...salva.listaNomes], ["Joana"]);
});

test("pagar mais um período: só pelo ícone, com a chave guardada, e só abre o Mercado Pago", async () => {
  const fundo = carregar();
  const chave = await licenca(20, { assinatura: undefined, pagamento: "123456789", precos: { mensal: 990, anual: 9900 } });
  const config = await fundo.doIcone({ tipo: "ativarLicenca", chave });
  assert.deepEqual({ ...config.pro.precos }, { mensal: 990, anual: 9900 });
  assert.match((await fundo.daPagina({ tipo: "pagarPeriodo", periodo: "mensal" })).erro, /ícone/);
  assert.match((await fundo.doIcone({ tipo: "pagarPeriodo", periodo: "vitalicio" })).erro, /1 mês ou 1 ano/);
  const resposta = await fundo.doIcone({ tipo: "pagarPeriodo", periodo: "mensal" });
  assert.equal(resposta.ok, true);
  assert.equal(resposta.precoMantido, true);
  assert.deepEqual(fundo.pagamentosPedidos.map((pedido) => pedido.chave), [chave]);
  assert.deepEqual(fundo.abasAbertas, ["https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=1"]);
  // Um servidor que devolvesse outro endereço não abre aba nenhuma.
  assert.match((await fundo.doIcone({ tipo: "pagarPeriodo", periodo: "anual" })).erro, /inesperado/);
  assert.equal(fundo.abasAbertas.length, 1);
  await fundo.doIcone({ tipo: "removerLicenca" });
  assert.match((await fundo.doIcone({ tipo: "pagarPeriodo", periodo: "mensal" })).erro, /Sem chave/);
});

test("cancelar a assinatura: só pelo ícone, com a chave guardada", async () => {
  const fundo = carregar();
  const config = await fundo.doIcone({ tipo: "ativarLicenca", chave: await licenca(30) });
  assert.equal(config.pro.assinatura, true);
  assert.match((await fundo.daPagina({ tipo: "cancelarAssinatura" })).erro, /ícone/);
  assert.equal(fundo.cancelamentos.length, 0);
  assert.match((await fundo.doIcone({ tipo: "cancelarAssinatura" })).mensagem, /cancelada/);
  assert.equal(fundo.cancelamentos.length, 1);
  const avulsa = await fundo.doIcone({ tipo: "ativarLicenca", chave: await licenca(20, { assinatura: undefined, pagamento: "1" }) });
  assert.equal(avulsa.pro.assinatura, false); // chave paga por período não mostra o botão
});

test("imagem colada num site de IA: só com o Pro, vai para o leitor e volta contada", async () => {
  const png = "data:image/png;base64,iVBORw0KGgo=";
  // Chrome e Edge: o leitor roda numa página escondida (offscreen), criada na primeira imagem.
  const fundo = carregar();
  const criados = [];
  const enviadosAoLeitor = [];
  fundo.contexto.chrome.offscreen = { createDocument: async (opcoes) => { criados.push(opcoes); } };
  fundo.contexto.chrome.runtime.getContexts = async () => criados.map(() => ({ contextType: "OFFSCREEN_DOCUMENT" }));
  fundo.contexto.chrome.runtime.sendMessage = async (mensagem) => {
    enviadosAoLeitor.push(mensagem);
    return { dados: "data:image/png;base64,AAAA", counts: { CPF: 1, QR_CODE: 1 } };
  };
  assert.match((await fundo.daPagina({ tipo: "protegerImagem", dados: png })).erro, /Véu Pro/);
  await fundo.doIcone({ tipo: "ativarLicenca", chave: await licenca(30) });
  assert.match((await fundo.daPagina({ tipo: "protegerImagem", dados: "javascript:alert(1)" })).erro, /inválida/);
  const resposta = await fundo.daPagina({ tipo: "protegerImagem", dados: png });
  assert.deepEqual({ ...resposta, counts: { ...resposta.counts } }, { dados: "data:image/png;base64,AAAA", counts: { CPF: 1, QR_CODE: 1 } });
  await fundo.daPagina({ tipo: "protegerImagem", dados: png });
  assert.equal(criados.length, 1); // a página escondida é reaproveitada
  assert.equal(criados[0].url, "leitor.html");
  assert.equal(enviadosAoLeitor[0].alvo, "leitor");
  assert.equal(enviadosAoLeitor[0].config.pro.ativo, true);
  assert.equal(fundo.store.session["contagem:7"].CPF, 2); // conta no selo da aba e no relatório

  // Firefox: a página de fundo tem o leitor (leitor.js) e lê ali mesmo.
  const firefox = carregar();
  firefox.contexto.veuLeitor = async ({ dados }) => ({ dados, counts: {} });
  await firefox.doIcone({ tipo: "ativarLicenca", chave: await licenca(30) });
  assert.equal((await firefox.daPagina({ tipo: "protegerImagem", dados: png })).dados, png);
});
