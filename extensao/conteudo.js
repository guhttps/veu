// Script de conteúdo: roda nas páginas das IAs, em um mundo isolado (a página não lê as variáveis daqui).
(() => {
  "use strict";
  if (window.__veuConteudo) return;
  window.__veuConteudo = true;

  const { Veu, Vault, LABELS, GROUPS } = window.veu;
  const PLACEHOLDER = /\[[A-Z][A-Z_]*[_\s-][0-9a-fA-F]{1,16}\]?/;
  const EDITAVEL = 'textarea, [contenteditable="true"], [contenteditable=""], [contenteditable="plaintext-only"]';

  // Os dados reais só aparecem na página se a pessoa ligar a opção: na página, o código do site também os lê.
  let config = { ativo: true, modo: "avisar", restaurarRespostas: false, bloquearTipos: [] };
  let veu = new Veu();
  let algumTipo = true; // com todas as caixinhas desmarcadas, a extensão não esconde nada
  let cofre = new Vault();
  let liberado = ""; // texto que a pessoa decidiu enviar mesmo assim

  // Configuração e cofre (o cofre fica na memória da sessão do navegador, por aba).
  function mensagem(dados) {
    try {
      return chrome.runtime.sendMessage(dados);
    } catch {
      return Promise.resolve(null); // extensão recarregada: esta página ficou órfã
    }
  }

  async function carregar() {
    const recebida = await mensagem({ tipo: "configuracao" });
    if (recebida) config = recebida;
    // Tipos: os da política da empresa (vazio = todos), menos os que a pessoa desmarcou no ícone da extensão.
    const permitidos = config.tipos?.length ? config.tipos : GROUPS.flatMap((grupo) => grupo.tipos);
    const ligados = permitidos.filter((tipo) => !(config.tiposDesligados || []).includes(tipo));
    algumTipo = ligados.length > 0;
    veu = new Veu({
      labels: ligados.length < permitidos.length || config.tipos?.length ? ligados : undefined,
      allowlist: config.ignorar || [],
      allowPatterns: config.ignorarPadroes || [],
      // Listas próprias (Véu Pro): nomes e termos que sempre somem, em qualquer grafia.
      terms: config.pro?.ativo ? { PESSOA: config.listaNomes || [], TERMO: config.listaTermos || [] } : undefined,
    });
    const salvo = await mensagem({ tipo: "carregarCofre" });
    if (salvo) cofre = Vault.fromJSON(salvo);
  }

  function salvarCofre(contagem) {
    mensagem({ tipo: "salvarCofre", cofre: cofre.toJSON() });
    if (contagem && Object.keys(contagem).length) mensagem({ tipo: "contar", contagem });
  }

  // Campo de mensagem
  function campoDe(alvo) {
    if (!(alvo instanceof Element)) return null;
    const campo = alvo.closest(EDITAVEL);
    if (!campo || campo.closest("#veu-raiz")) return null;
    if (campo.tagName === "TEXTAREA" && (campo.readOnly || campo.disabled)) return null;
    return campo;
  }

  const textoDo = (campo) => (campo.tagName === "TEXTAREA" ? campo.value : campo.innerText);

  function selecionarTudo(campo) {
    campo.focus();
    if (campo.tagName === "TEXTAREA") {
      campo.select();
      return;
    }
    const intervalo = document.createRange();
    intervalo.selectNodeContents(campo);
    const selecao = window.getSelection();
    selecao.removeAllRanges();
    selecao.addRange(intervalo);
  }

  /** Insere texto onde está o cursor usando o próprio mecanismo de colar do site (ProseMirror, Lexical, Quill...). */
  function inserir(campo, texto) {
    const antes = textoDo(campo);
    if (campo.tagName !== "TEXTAREA") {
      const dados = new DataTransfer();
      dados.setData("text/plain", texto);
      const colar = new ClipboardEvent("paste", { clipboardData: dados, bubbles: true, cancelable: true });
      campo.dispatchEvent(colar);
      if (colar.defaultPrevented && textoDo(campo) !== antes) return;
    }
    if (document.execCommand("insertText", false, texto)) return;
    // Último recurso para textarea: valor + evento de input (React percebe pelo setter nativo).
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    setter.call(campo, texto);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function substituirTudo(campo, texto) {
    selecionarTudo(campo);
    inserir(campo, texto);
  }

  function proteger(texto) {
    const resultado = veu.anonymize(texto, cofre);
    salvarCofre(resultado.counts());
    return resultado;
  }

  const tiposBloqueados = (entidades) =>
    [...new Set(entidades.map((e) => e.label).filter((rotulo) => (config.bloquearTipos || []).includes(rotulo)))];

  const nome = (rotulo) => (LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, "");

  function resumo(entidades) {
    const contagem = {};
    for (const entidade of entidades) contagem[entidade.label] = (contagem[entidade.label] || 0) + 1;
    return Object.entries(contagem).map(([rotulo, n]) => `${n} ${nome(rotulo)}`).join(", ");
  }

  // Aviso flutuante (shadow DOM: o CSS do site não interfere).
  let raiz = null;
  // Orientação da empresa (política gerenciada): só links https, sempre como texto, nunca como HTML.
  function linkSeguro(valor) {
    try {
      const url = new URL(String(valor || ""));
      return url.protocol === "https:" ? url.href : null;
    } catch {
      return null;
    }
  }

  function aviso(texto, acoes = [], tipo = "info", orientar = tipo !== "info") {
    if (!raiz) {
      const hospedeiro = document.createElement("div");
      hospedeiro.id = "veu-raiz";
      document.documentElement.append(hospedeiro);
      raiz = hospedeiro.attachShadow({ mode: "closed" });
      const estilo = document.createElement("style");
      estilo.textContent = `
        .caixa { position: fixed; z-index: 2147483647; left: 50%; bottom: 96px; transform: translateX(-50%);
          max-width: min(560px, calc(100vw - 32px)); background: #1d2522; color: #f3f6f4; border-radius: 12px;
          padding: 12px 14px; font: 14px/1.45 system-ui, sans-serif; box-shadow: 0 8px 28px rgba(0,0,0,.28);
          display: flex; gap: 10px; align-items: center; flex-wrap: wrap; border-left: 4px solid #6fb3b8; }
        .caixa.alerta { border-left-color: #e3a33b; } .caixa.bloqueio { border-left-color: #e5534b; }
        .texto { flex: 1 1 260px; } .marca { font-weight: 700; margin-right: 4px; }
        button { font: 600 13px system-ui, sans-serif; border-radius: 8px; padding: 7px 11px; cursor: pointer;
          border: 1px solid #4b5753; background: transparent; color: inherit; }
        button.principal { background: #6fb3b8; border-color: #6fb3b8; color: #0d1413; }
        .orientacao { margin-top: 6px; color: #c9d4cf; font-size: 13px; } .orientacao a { color: #8fd0d4; }`;
      raiz.append(estilo);
    }
    raiz.querySelector(".caixa")?.remove();
    if (!texto) return;
    const caixa = document.createElement("div");
    caixa.className = `caixa ${tipo}`;
    caixa.setAttribute("role", "status");
    const conteudo = document.createElement("div");
    conteudo.className = "texto";
    const marca = document.createElement("span");
    marca.className = "marca";
    marca.textContent = "Véu";
    conteudo.append(marca, texto);
    const orientacao = orientar && config.orientacao ? String(config.orientacao).slice(0, 500) : "";
    if (orientacao) {
      const linha = document.createElement("div");
      linha.className = "orientacao";
      linha.textContent = orientacao;
      const link = linkSeguro(config.linkOrientacao);
      if (link) {
        const ancora = document.createElement("a");
        ancora.href = link;
        ancora.target = "_blank";
        ancora.rel = "noopener noreferrer";
        ancora.textContent = "Saiba mais";
        linha.append(" ", ancora);
      }
      conteudo.append(linha);
    }
    caixa.append(conteudo);
    for (const acao of [...acoes, { rotulo: "Fechar", fazer: () => aviso("") }]) {
      const botao = document.createElement("button");
      botao.textContent = acao.rotulo;
      if (acao.principal) botao.className = "principal";
      botao.addEventListener("click", (evento) => {
        evento.preventDefault();
        acao.fazer();
      });
      caixa.append(botao);
    }
    raiz.append(caixa);
    clearTimeout(aviso.tempo);
    if (!acoes.length) aviso.tempo = setTimeout(() => caixa.remove(), orientacao ? 9000 : 5000);
  }

  function oferecerProtecao(campo, entidades) {
    const bloqueados = tiposBloqueados(entidades);
    const mensagemTexto = bloqueados.length
      ? `Este texto tem ${resumo(entidades)}. ${bloqueados.map(nome).join(", ")} não pode ser enviado à IA.`
      : `Este texto tem ${resumo(entidades)}.`;
    const acoes = [{
      rotulo: "Proteger", principal: true, fazer: () => {
        const resultado = proteger(textoDo(campo));
        substituirTudo(campo, resultado.text);
        aviso("Dados trocados por marcadores. Confira e envie.");
      },
    }];
    if (!bloqueados.length && config.modo !== "bloquear") {
      acoes.push({ rotulo: "Enviar assim", fazer: () => { liberado = textoDo(campo); aviso(""); } });
    }
    aviso(mensagemTexto, acoes, bloqueados.length || config.modo === "bloquear" ? "bloqueio" : "alerta");
  }

  // Imagens (Véu Pro): um print colado, arrastado ou anexado chega ao site já com tarjas sobre os dados e os QR
  // Codes. O leitor roda numa página da extensão (fundo.js); se ele falhar, a imagem não é enviada.
  const IMAGEM = /^image\/(png|jpeg|webp|gif|bmp)$/;
  const temImagens = (lista) => Boolean(config.pro?.ativo) && [...(lista || [])].some((arquivo) => IMAGEM.test(arquivo.type));
  const lerDataUrl = (blob) => new Promise((pronto, erro) => {
    const leitor = new FileReader();
    leitor.onload = () => pronto(leitor.result);
    leitor.onerror = () => erro(leitor.error);
    leitor.readAsDataURL(blob);
  });
  function blobDe(dataUrl) {
    const binario = atob(dataUrl.split(",")[1]);
    const bytes = new Uint8Array(binario.length);
    for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
    return new Blob([bytes], { type: "image/png" });
  }
  const resumoDaContagem = (contagem) => Object.entries(contagem).map(([rotulo, n]) => `${n} ${nome(rotulo)}`).join(", ");

  async function protegerArquivos(arquivos) {
    const protegidos = [];
    const contagem = {};
    for (const arquivo of arquivos) {
      if (!IMAGEM.test(arquivo.type)) {
        protegidos.push(arquivo);
        continue;
      }
      const resposta = await mensagem({ tipo: "protegerImagem", dados: await lerDataUrl(arquivo) });
      if (!resposta || resposta.erro) throw new Error(resposta?.erro || "o leitor de imagens não respondeu.");
      const nomeBase = arquivo.name.replace(/\.[^.]+$/, "") || "imagem";
      protegidos.push(new File([blobDe(resposta.dados)], `${nomeBase}-protegido.png`, { type: "image/png" }));
      for (const [rotulo, n] of Object.entries(resposta.counts || {})) contagem[rotulo] = (contagem[rotulo] || 0) + n;
    }
    return { protegidos, contagem };
  }

  /** Protege as imagens e entrega ao site um evento novo (colar, soltar ou trocar o anexo) com as versões protegidas. */
  async function entregarProtegidas(alvo, arquivos, criarEvento, texto = "") {
    aviso("Véu Pro: lendo a imagem para cobrir os dados...", [], "info", false);
    try {
      const { protegidos, contagem } = await protegerArquivos(arquivos);
      const dados = new DataTransfer();
      for (const arquivo of protegidos) dados.items.add(arquivo);
      if (texto) dados.setData("text/plain", veu.analyze(texto).length ? proteger(texto).text : texto);
      alvo.dispatchEvent(criarEvento(dados));
      const partes = resumoDaContagem(contagem);
      aviso(partes ? `Imagem protegida com tarjas: ${partes}.` : "Imagem conferida: nenhum dado pessoal encontrado.",
        [], "info", true);
    } catch (erro) {
      aviso(`O Véu não conseguiu proteger a imagem, e ela não foi enviada (${erro.message}).`, [], "alerta");
    }
  }

  window.addEventListener("drop", (evento) => {
    if (!config.ativo || !algumTipo || !evento.isTrusted || !temImagens(evento.dataTransfer?.files)) return;
    const arquivos = [...evento.dataTransfer.files];
    evento.preventDefault();
    evento.stopImmediatePropagation();
    const { clientX, clientY } = evento;
    entregarProtegidas(evento.target, arquivos,
      (dados) => new DragEvent("drop", { dataTransfer: dados, bubbles: true, cancelable: true, clientX, clientY }));
  }, true);

  // Anexo pelo botão do site (campo de arquivo): o site não vê o original; o campo recebe a versão protegida.
  const anexoComImagens = (evento) => evento.isTrusted && config.ativo && algumTipo && evento.target instanceof HTMLInputElement
    && evento.target.type === "file" && temImagens(evento.target.files);
  window.addEventListener("input", (evento) => {
    if (anexoComImagens(evento)) evento.stopImmediatePropagation();
  }, true);
  window.addEventListener("change", (evento) => {
    if (!anexoComImagens(evento)) return;
    evento.stopImmediatePropagation();
    const entrada = evento.target;
    entregarProtegidas(entrada, [...entrada.files], (dados) => {
      entrada.files = dados.files;
      entrada.dispatchEvent(new Event("input", { bubbles: true }));
      return new Event("change", { bubbles: true });
    });
  }, true);

  // Colar: o texto com dados entra já protegido (modos proteger e bloquear) ou com um aviso (modo avisar).
  window.addEventListener("paste", (evento) => {
    if (!config.ativo || !algumTipo || !evento.isTrusted) return;
    if (temImagens(evento.clipboardData?.files)) {
      const arquivos = [...evento.clipboardData.files];
      const texto = evento.clipboardData.getData("text/plain");
      evento.preventDefault();
      evento.stopImmediatePropagation();
      entregarProtegidas(evento.target, arquivos,
        (dados) => new ClipboardEvent("paste", { clipboardData: dados, bubbles: true, cancelable: true }), texto);
      return;
    }
    const campo = campoDe(evento.target);
    const texto = evento.clipboardData?.getData("text/plain");
    if (!campo || !texto) return;
    const entidades = veu.analyze(texto);
    if (!entidades.length) return;
    if (config.modo === "avisar" && !tiposBloqueados(entidades).length) {
      setTimeout(() => oferecerProtecao(campo, veu.analyze(textoDo(campo))), 50);
      return;
    }
    evento.preventDefault();
    evento.stopImmediatePropagation();
    const resultado = proteger(texto);
    inserir(campo, resultado.text);
    aviso(`Protegido ao colar: ${resumo(entidades)}.`, [], "info", true);
  }, true);

  // Enviar: Enter ou botão de enviar com dados ainda visíveis.
  function deveSegurar(campo) {
    if (!config.ativo || !algumTipo || !campo) return false;
    const texto = textoDo(campo);
    if (!texto.trim() || texto === liberado) return false;
    const entidades = veu.analyze(texto);
    if (!entidades.length) return false;
    if (config.modo === "avisar" && !tiposBloqueados(entidades).length) {
      oferecerProtecao(campo, entidades);
      return false; // avisa, mas não segura o envio
    }
    if (config.modo === "proteger" && !tiposBloqueados(entidades).length) {
      substituirTudo(campo, proteger(texto).text);
      aviso("Protegi os dados antes de enviar. Confira e envie de novo.", [], "info", true);
      return true;
    }
    oferecerProtecao(campo, entidades);
    return true;
  }

  window.addEventListener("keydown", (evento) => {
    if (evento.key !== "Enter" || evento.shiftKey || evento.isComposing || !evento.isTrusted) return;
    if (deveSegurar(campoDe(evento.target))) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
    }
  }, true);

  const BOTAO_ENVIAR = /send|enviar|submit|mandar/i;
  window.addEventListener("click", (evento) => {
    if (!evento.isTrusted) return;
    const botao = evento.target instanceof Element ? evento.target.closest("button, [role=button]") : null;
    if (!botao) return;
    const descricao = `${botao.getAttribute("aria-label") || ""} ${botao.getAttribute("data-testid") || ""} ${botao.type === "submit" ? "submit" : ""}`;
    if (!BOTAO_ENVIAR.test(descricao)) return;
    const campo = campoDe(document.activeElement) || campoDe(botao.closest("form")?.querySelector(EDITAVEL)) ||
      campoDe(document.querySelector("#prompt-textarea, div.ProseMirror, rich-textarea .ql-editor, textarea"));
    if (deveSegurar(campo)) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
    }
  }, true);

  // Respostas: os marcadores viram os dados reais, só na tela desta pessoa.
  const pendentes = new Set();
  let agendado = false;
  function restaurarNos() {
    agendado = false;
    if (!config.restaurarRespostas || !cofre.size) {
      pendentes.clear();
      return;
    }
    for (const no of pendentes) {
      if (!no.isConnected) continue;
      if (no.nodeType === Node.TEXT_NODE) restaurarTexto(no);
      else {
        const andarilho = document.createTreeWalker(no, NodeFilter.SHOW_TEXT);
        for (let atual = andarilho.nextNode(); atual; atual = andarilho.nextNode()) restaurarTexto(atual);
      }
    }
    pendentes.clear();
  }
  function restaurarTexto(no) {
    if (!PLACEHOLDER.test(no.data)) return;
    const pai = no.parentElement;
    if (!pai || pai.closest(EDITAVEL) || pai.closest("#veu-raiz, script, style")) return;
    const restaurado = cofre.restore(no.data);
    if (restaurado !== no.data) no.data = restaurado;
  }
  new MutationObserver((mudancas) => {
    for (const mudanca of mudancas) {
      if (mudanca.type === "characterData") pendentes.add(mudanca.target);
      else for (const no of mudanca.addedNodes) pendentes.add(no);
    }
    if (pendentes.size && !agendado) {
      agendado = true;
      requestAnimationFrame(restaurarNos);
    }
  }).observe(document.documentElement, { childList: true, subtree: true, characterData: true });

  // Menus e popup
  chrome.runtime.onMessage.addListener((pedido, _remetente, responder) => {
    if (pedido.tipo === "restaurar") {
      responder({ texto: cofre.restore(pedido.texto || "") });
    } else if (pedido.tipo === "protegerSelecao") {
      const campo = campoDe(document.activeElement);
      const selecionado = window.getSelection()?.toString() ||
        (campo?.tagName === "TEXTAREA" ? campo.value.slice(campo.selectionStart, campo.selectionEnd) : "");
      if (campo && selecionado) {
        const resultado = proteger(selecionado);
        inserir(campo, resultado.text);
        aviso(resultado.replacements.length ? `Protegido: ${resumo(resultado.entities)}.` : "Nenhum dado pessoal na seleção.");
      }
      responder({ ok: true });
    } else if (pedido.tipo === "restaurarSelecao") {
      const texto = cofre.restore(window.getSelection()?.toString() || "");
      navigator.clipboard.writeText(texto).then(
        () => aviso("Seleção copiada com os dados reais."),
        () => aviso("Não consegui copiar. Use o botão Restaurar no ícone do Véu."),
      );
      responder({ ok: true });
    } else if (pedido.tipo === "recarregar") {
      carregar().then(() => responder({ ok: true }));
      return true;
    }
    return false;
  });

  // O script roda antes de a página montar (document_start), para tratar o colar antes do código do site.
  carregar().then(() => {
    const comecar = () => {
      pendentes.add(document.body);
      restaurarNos();
    };
    if (document.body) comecar();
    else document.addEventListener("DOMContentLoaded", comecar, { once: true });
  });
})();
