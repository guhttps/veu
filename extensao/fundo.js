// Service worker da extensão: configuração (política da empresa + escolhas do usuário), cofre por aba e menus.
"use strict";
// Licença do Véu Pro (licenca.js). No Firefox, a página de fundo já carrega o arquivo antes deste.
if (typeof importScripts === "function" && !globalThis.veuLicenca) importScripts("licenca.js");

const HORA = 3600 * 1000;
const DIA = 24 * HORA;
const LIMITE_LISTA = 2000; // itens por lista própria

const PADRAO = {
  ativo: true,
  modo: "avisar",
  tipos: [],
  tiposDesligados: [], // caixinhas desmarcadas pela pessoa no ícone da extensão
  bloquearTipos: [],
  ignorar: [],
  ignorarPadroes: [],
  restaurarRespostas: false, // na página, o código do site também leria os dados reais
  travarConfiguracao: false,
  orientacao: "", // mensagem da empresa nos avisos (política gerenciada)
  linkOrientacao: "",
  listaNomes: [], // listas próprias (Pro): ficam só neste navegador, em storage.local
  listaTermos: [],
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
  // As listas próprias têm nomes de clientes: ficam em storage.local, fora da sincronização da conta do navegador.
  const listas = await chrome.storage.local.get(["listaNomes", "listaTermos"]);
  const final = { ...PADRAO, ...usuario, ...listas, ...empresa };
  final.gerenciada = Object.keys(empresa).length > 0;
  final.camposDaEmpresa = Object.keys(empresa);
  final.pro = await estadoPro(empresa);
  return final;
}

// Véu Pro ------------------------------------------------------------------------------------------------------
let renovando = null;

/** Situação da licença: a da empresa (política) ou a colada no ícone. Perto do vencimento, renova sozinha. */
async function estadoPro(empresa) {
  const licencas = globalThis.veuLicenca;
  const salvo = await chrome.storage.local.get(["licenca", "licencaTentativa"]);
  const chave = empresa.licenca || salvo.licenca;
  if (!chave || !licencas) return { ativo: false };
  const resultado = await licencas.verificar(chave);
  const licenca = resultado.licenca;
  const faltam = licenca ? licenca.exp * 1000 - Date.now() : Infinity;
  if (renovavel(licenca) && !empresa.licenca && faltam < 7 * DIA
    && Date.now() - (salvo.licencaTentativa || 0) > 12 * HORA) {
    renovando ??= renovarLicenca(chave).finally(() => { renovando = null; });
  }
  return { ativo: resultado.valida, motivo: resultado.motivo, plano: licenca?.plano, email: licenca?.email,
    exp: licenca?.exp, daEmpresa: Boolean(empresa.licenca), avulsa: Boolean(licenca?.pagamento && !licenca.assinatura),
    acabando: faltam < 7 * DIA };
}

// Só a chave de uma assinatura renova sozinha. A paga por período (Pix, boleto) e a emitida à mão, não: sem rede.
function renovavel(licenca) {
  return Boolean(licenca?.assinatura) && !String(licenca.assinatura).startsWith("manual");
}

// No Firefox, a renovação depende da permissão opcional de dados que o popup pede ao ativar a chave.
const DADOS_DA_RENOVACAO = ["authenticationInfo", "personallyIdentifyingInfo"];
async function podeRenovar() {
  const permissoes = globalThis.browser?.permissions;
  if (!permissoes?.contains || !/Firefox\//.test(globalThis.navigator?.userAgent || "")) return true;
  try {
    return await permissoes.contains({ data_collection: DADOS_DA_RENOVACAO });
  } catch {
    return true; // Firefox sem o recurso de permissões de dados
  }
}

async function renovarLicenca(chave) {
  if (!(await podeRenovar())) return { erro: "Sem permissão para renovar a chave." };
  await chrome.storage.local.set({ licencaTentativa: Date.now() });
  const resposta = await globalThis.veuLicenca.renovar(chave);
  if (resposta.chave && (await globalThis.veuLicenca.verificar(resposta.chave)).valida) {
    await chrome.storage.local.set({ licenca: resposta.chave });
  }
  return resposta;
}

const MOTIVOS = {
  formato: "Isto não parece uma chave do Véu: ela começa com VEU1.",
  assinatura: "Esta chave não foi emitida pelo Véu.",
  vencida: "Esta chave venceu. Se a assinatura está ativa, o Véu tenta renovar sozinho.",
  "sem-chave-publica": "O Véu Pro ainda não foi lançado.",
};

// Relatório mensal (Pro): só contagens por mês, tipo, site e dia. Nenhum texto e nenhum valor ficam guardados.
const MESES_NO_RELATORIO = 13;
let gravandoRelatorio = Promise.resolve();

function registrarNoRelatorio(contagem, endereco) {
  const tarefa = async () => {
    const total = Object.values(contagem || {}).reduce((soma, n) => soma + n, 0);
    if (!total || !(await estadoPro(await politica())).ativo) return;
    let site = "arquivos protegidos";
    if (endereco !== "arquivos") {
      try {
        site = new URL(endereco).hostname.replace(/^www\./, "") || "outro";
      } catch {
        site = "outro";
      }
    }
    const agora = new Date();
    const mes = `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}`;
    const { relatorio = {} } = await chrome.storage.local.get("relatorio");
    const atual = relatorio[mes] ||= { tipos: {}, sites: {}, dias: {}, envios: 0 };
    for (const [rotulo, n] of Object.entries(contagem)) atual.tipos[rotulo] = (atual.tipos[rotulo] || 0) + n;
    atual.sites[site] = (atual.sites[site] || 0) + total;
    const dia = String(agora.getDate());
    atual.dias[dia] = (atual.dias[dia] || 0) + total;
    atual.envios += 1;
    for (const velho of Object.keys(relatorio).sort().slice(0, -MESES_NO_RELATORIO)) delete relatorio[velho];
    await chrome.storage.local.set({ relatorio });
  };
  gravandoRelatorio = gravandoRelatorio.then(tarefa, tarefa); // uma gravação por vez, sem perder contagens
  return gravandoRelatorio;
}

const limparLista = (lista) => (Array.isArray(lista) ? lista : [])
  .map((item) => String(item).trim().slice(0, 200)).filter((item) => item.length >= 2).slice(0, LIMITE_LISTA);

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
  // Páginas da própria extensão (o ícone, também aberto numa aba); o script dentro dos sites de IA não conta.
  const daExtensao = (remetente.url || "").startsWith(chrome.runtime.getURL(""));
  // A página de arquivos usa o cofre da aba da IA (abaId); o script de uma página só usa o da própria aba.
  const abaId = (daExtensao && mensagem.abaId) || (remetente.tab?.id ?? mensagem.abaId);
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
        await registrarNoRelatorio(mensagem.contagem, daExtensao ? "arquivos" : remetente.tab?.url || remetente.url);
        return atual;
      }
      case "relatorio": {
        if (!daExtensao) return { erro: "O relatório só abre pelo ícone do Véu." };
        const config = await configuracao();
        const { relatorio = {} } = await chrome.storage.local.get("relatorio");
        return { pro: config.pro, meses: config.pro.ativo ? relatorio : {} };
      }
      case "apagarRelatorio":
        if (!daExtensao) return { erro: "O relatório só muda pelo ícone do Véu." };
        await chrome.storage.local.remove("relatorio");
        return { meses: {} };
      case "contagem":
        return (await chrome.storage.session.get(chaveDaContagem(abaId)))[chaveDaContagem(abaId)] || {};
      case "ativarLicenca": {
        if (!daExtensao) return { erro: "A chave só é ativada pelo ícone do Véu." };
        const chave = String(mensagem.chave || "").trim();
        const resultado = await globalThis.veuLicenca.verificar(chave);
        if (!resultado.valida && resultado.motivo !== "vencida") return { erro: MOTIVOS[resultado.motivo] || "Chave inválida." };
        if (!resultado.valida && !renovavel(resultado.licenca)) {
          const data = new Date(resultado.licenca.exp * 1000).toLocaleDateString("pt-BR");
          return { erro: `Esta chave venceu em ${data}. Para continuar, pague mais um período na página de planos.` };
        }
        await chrome.storage.local.set({ licenca: chave, licencaTentativa: 0 });
        if (!resultado.valida) await renovarLicenca(chave);
        return configuracao();
      }
      case "removerLicenca":
        if (!daExtensao) return { erro: "A chave só é removida pelo ícone do Véu." };
        await chrome.storage.local.remove(["licenca", "licencaTentativa"]);
        return configuracao();
      case "salvarListas": {
        if (!daExtensao) return { erro: "As listas só mudam pelo ícone do Véu." };
        const atual = await configuracao();
        if (!atual.pro.ativo) return { erro: "As listas próprias fazem parte do Véu Pro." };
        const listas = { listaNomes: limparLista(mensagem.listaNomes), listaTermos: limparLista(mensagem.listaTermos) };
        for (const campo of atual.camposDaEmpresa) delete listas[campo];
        await chrome.storage.local.set(listas);
        return configuracao();
      }
      case "salvarPreferencias": {
        // Só o popup muda as preferências: o script que roda dentro dos sites de IA nunca desliga a proteção.
        if (!daExtensao) return { erro: "As preferências só mudam pelo ícone do Véu." };
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
