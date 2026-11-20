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
  const contexto = {
    console, crypto, TextEncoder, TextDecoder, atob, btoa,
    chrome: {
      storage: { managed: { get: async () => ({ ...politica }) }, sync: area("sync"), session: area("session"), local: area("local") },
      runtime: { onMessage: { addListener: (fn) => { receptor = fn; } }, onInstalled: evento(),
        getURL: (caminho) => `chrome-extension://veu/${caminho}` },
      tabs: { onRemoved: evento() }, contextMenus: { onClicked: evento() },
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
  };
  vm.createContext(contexto);
  vm.runInContext(readFileSync(new URL("fundo.js", pasta), "utf8"), contexto);
  const enviar = (mensagem, remetente) => new Promise((resolver) => receptor(mensagem, remetente, resolver));
  return {
    store, renovacoes,
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
