// Service worker da extensão: configuração (política da empresa + escolhas do usuário), cofre por aba e menus.
"use strict";

const PADRAO = {
  ativo: true,
  modo: "avisar",
  tipos: [],
  bloquearTipos: [],
  ignorar: [],
  ignorarPadroes: [],
  restaurarRespostas: false, // na página, o código do site também leria os dados reais
  travarConfiguracao: false,
  orientacao: "", // mensagem da empresa nos avisos (política gerenciada)
  linkOrientacao: "",
};

async function politica() {
  try {
    return (await chrome.storage.managed.get(null)) || {};
  } catch {
    return {}; // Firefox sem política, ou navegador sem suporte
  }
}

/** A política da empresa vence as escolhas do usuário; com travarConfiguracao, o usuário não muda nada. */
async function configuracao() {
  const empresa = await politica();
  const usuario = empresa.travarConfiguracao ? {} : await chrome.storage.sync.get(null);
  const final = { ...PADRAO, ...usuario, ...empresa };
  final.gerenciada = Object.keys(empresa).length > 0;
  final.camposDaEmpresa = Object.keys(empresa);
  return final;
}

const chaveDoCofre = (abaId) => `cofre:${abaId}`;
const chaveDaContagem = (abaId) => `contagem:${abaId}`;

async function atualizarSelo(abaId) {
  const salvo = await chrome.storage.session.get(chaveDaContagem(abaId));
  const contagem = salvo[chaveDaContagem(abaId)] || {};
  const total = Object.values(contagem).reduce((soma, n) => soma + n, 0);
  await chrome.action.setBadgeBackgroundColor({ color: "#234e52", tabId: abaId });
  await chrome.action.setBadgeText({ text: total ? String(Math.min(total, 999)) : "", tabId: abaId });
}

chrome.runtime.onMessage.addListener((mensagem, remetente, responder) => {
  const abaId = remetente.tab?.id ?? mensagem.abaId;
  (async () => {
    switch (mensagem.tipo) {
      case "configuracao":
        return configuracao();
      case "salvarCofre":
        await chrome.storage.session.set({ [chaveDoCofre(abaId)]: mensagem.cofre });
        return true;
      case "carregarCofre":
        return (await chrome.storage.session.get(chaveDoCofre(abaId)))[chaveDoCofre(abaId)] || null;
      case "contar": {
        const chave = chaveDaContagem(abaId);
        const atual = (await chrome.storage.session.get(chave))[chave] || {};
        for (const [rotulo, n] of Object.entries(mensagem.contagem || {})) atual[rotulo] = (atual[rotulo] || 0) + n;
        await chrome.storage.session.set({ [chave]: atual });
        await atualizarSelo(abaId);
        return atual;
      }
      case "contagem":
        return (await chrome.storage.session.get(chaveDaContagem(abaId)))[chaveDaContagem(abaId)] || {};
      case "salvarPreferencias": {
        const atual = await configuracao();
        if (atual.travarConfiguracao) return { erro: "A configuração é definida pela sua empresa." };
        const permitidas = Object.fromEntries(
          Object.entries(mensagem.preferencias).filter(([chave]) => !atual.camposDaEmpresa.includes(chave)),
        );
        await chrome.storage.sync.set(permitidas);
        return configuracao();
      }
      default:
        return null;
    }
  })().then(responder, (erro) => responder({ erro: String(erro) }));
  return true;
});

chrome.tabs.onRemoved.addListener((abaId) => {
  chrome.storage.session.remove([chaveDoCofre(abaId), chaveDaContagem(abaId)]);
});

chrome.runtime.onInstalled.addListener(() => {
  // O cofre fica só na memória da sessão do navegador, nunca no disco, e só a extensão o lê.
  chrome.storage.session.setAccessLevel?.({ accessLevel: "TRUSTED_CONTEXTS" });
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "proteger", title: "Véu: proteger o texto selecionado", contexts: ["editable"] });
    chrome.contextMenus.create({ id: "restaurar", title: "Véu: copiar a seleção com os dados reais", contexts: ["selection"] });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, aba) => {
  if (!aba?.id) return;
  const mensagem = { tipo: info.menuItemId === "proteger" ? "protegerSelecao" : "restaurarSelecao" };
  try {
    await chrome.tabs.sendMessage(aba.id, mensagem);
  } catch {
    // Fora dos sites de IA: o clique no menu dá acesso só a esta aba (activeTab), e o Véu entra só agora.
    await chrome.scripting.executeScript({ target: { tabId: aba.id }, files: ["veu.global.js", "conteudo.js"] });
    await chrome.tabs.sendMessage(aba.id, mensagem).catch(() => {});
  }
});
