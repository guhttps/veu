"use strict";
// Véu Pro: arquivos inteiros. Usa o cofre da aba da IA de onde a página foi aberta, para os dados reais também
// voltarem nas respostas do chat. Nada sai do navegador; o PDF é lido pelo pdf.js que vem junto com a extensão.
(async () => {
  const $ = (seletor) => document.querySelector(seletor);
  const { Veu, Vault, LABELS, GROUPS, protectDocument, restoreDocument, documentKind } = window.veu;
  const parametros = new URLSearchParams(location.search);
  const abaId = Number(parametros.get("aba")) || "arquivos";
  const site = parametros.get("site") || "";
  const LIMITE = 100 * 1024 * 1024;
  const TEXTO = new Set(["txt", "md", "csv", "json"]);

  const config = await chrome.runtime.sendMessage({ tipo: "configuracao" });
  $("#sem-pro").hidden = Boolean(config.pro?.ativo);
  $("#conteudo").hidden = !config.pro?.ativo;
  if (!config.pro?.ativo) return;
  $("#aba").textContent = site
    ? `Usando os marcadores da aba ${site}: as respostas da IA nessa aba também voltam com os dados reais.`
    : "Sem aba de IA: os marcadores valem só para devolver os dados por esta página.";

  // Mesma configuração da extensão nos sites de IA: tipos, valores ignorados e listas próprias.
  const permitidos = config.tipos?.length ? config.tipos : GROUPS.flatMap((grupo) => grupo.tipos);
  const ligados = permitidos.filter((tipo) => !(config.tiposDesligados || []).includes(tipo));
  const veu = new Veu({
    labels: ligados.length < permitidos.length || config.tipos?.length ? ligados : undefined,
    allowlist: config.ignorar || [],
    allowPatterns: config.ignorarPadroes || [],
    terms: { PESSOA: config.listaNomes || [], TERMO: config.listaTermos || [] },
  });

  async function cofre() {
    const salvo = await chrome.runtime.sendMessage({ tipo: "carregarCofre", abaId });
    return salvo ? Vault.fromJSON(salvo) : new Vault();
  }

  async function guardar(vault, contagem) {
    await chrome.runtime.sendMessage({ tipo: "salvarCofre", abaId, cofre: vault.toJSON() });
    if (Object.keys(contagem).length) await chrome.runtime.sendMessage({ tipo: "contar", abaId, contagem });
    if (typeof abaId === "number") chrome.tabs.sendMessage(abaId, { tipo: "recarregar" }).catch(() => {});
  }

  async function textoDoPdf(bytes) {
    const pdfjs = await import(chrome.runtime.getURL("pdf.min.mjs"));
    pdfjs.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL("pdf.worker.min.mjs");
    const documento = await pdfjs.getDocument({ data: bytes, isEvalSupported: false }).promise;
    const paginas = [];
    for (let numero = 1; numero <= documento.numPages; numero++) {
      const conteudo = await (await documento.getPage(numero)).getTextContent();
      const texto = conteudo.items.map((item) => item.str + (item.hasEOL ? "\n" : "")).join("").trim();
      if (texto) paginas.push(`## Página ${numero}\n\n${texto}`);
    }
    return paginas.join("\n\n");
  }

  const extensao = (nome) => nome.toLowerCase().split(".").pop();
  const base = (nome) => nome.replace(/\.[^.]+$/, "");
  // "Nome de pessoa" vira "nome de pessoa", mas siglas como CPF e IBAN ficam em maiúsculas.
  const minuscula = (nome) => (/^\p{Lu}[\p{Ll}-]/u.test(nome) ? nome[0].toLowerCase() + nome.slice(1) : nome);
  const resumo = (contagem) => Object.entries(contagem)
    .map(([rotulo, n]) => `${n} ${minuscula((LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, ""))}`).join(", ");

  function baixar(bytes, nome, tipo) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([bytes], { type: tipo || "application/octet-stream" }));
    link.download = nome;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  }

  function registrar(texto, erro = false) {
    $("#vazio").hidden = true;
    const linha = document.createElement("div");
    const nome = document.createElement("span");
    nome.textContent = texto;
    if (erro) nome.style.color = "#b0402b";
    linha.append(nome);
    $("#feitos").prepend(linha);
  }

  async function proteger(arquivo) {
    if (arquivo.size > LIMITE) return registrar(`${arquivo.name}: maior que 100 MB.`, true);
    const tipo = extensao(arquivo.name);
    const vault = await cofre();
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    let saida;
    let contagem = {};
    let nome;
    if (documentKind(arquivo.name)) {
      ({ bytes: saida, counts: contagem } = await protectDocument(bytes, documentKind(arquivo.name), veu, vault));
      nome = `${base(arquivo.name)}-protegido.${tipo}`;
    } else {
      const texto = tipo === "pdf" ? await textoDoPdf(bytes) : new TextDecoder().decode(bytes);
      const resultado = veu.anonymize(texto, vault);
      contagem = resultado.counts();
      saida = new TextEncoder().encode(resultado.text);
      nome = `${base(arquivo.name)}-protegido.${tipo === "pdf" ? "txt" : tipo}`;
    }
    await guardar(vault, contagem);
    baixar(saida, nome, arquivo.type);
    registrar(`${nome}: ${Object.keys(contagem).length ? `escondidos ${resumo(contagem)}` : "nenhum dado pessoal encontrado"}.`);
  }

  async function restaurar(arquivo) {
    if (arquivo.size > LIMITE) return registrar(`${arquivo.name}: maior que 100 MB.`, true);
    const tipo = extensao(arquivo.name);
    const vault = await cofre();
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    let saida;
    if (documentKind(arquivo.name)) saida = await restoreDocument(bytes, documentKind(arquivo.name), vault);
    else if (TEXTO.has(tipo)) saida = new TextEncoder().encode(vault.restore(new TextDecoder().decode(bytes)));
    else return registrar(`${arquivo.name}: para PDF, devolva os dados no texto gerado a partir dele.`, true);
    const nome = `${base(arquivo.name).replace(/-protegido$/, "")}-com-dados.${tipo}`;
    baixar(saida, nome, arquivo.type);
    registrar(`${nome}: dados reais devolvidos.`);
  }

  function ligar(entrada, area, acao) {
    const executar = async (arquivo) => {
      try {
        await acao(arquivo);
      } catch (erro) {
        registrar(`${arquivo.name}: ${erro.message || "não consegui ler o arquivo."}`, true);
      }
    };
    entrada.addEventListener("change", () => {
      for (const arquivo of entrada.files) executar(arquivo);
      entrada.value = "";
    });
    area.addEventListener("dragover", (evento) => { evento.preventDefault(); area.classList.add("ativo"); });
    area.addEventListener("dragleave", () => area.classList.remove("ativo"));
    area.addEventListener("drop", (evento) => {
      evento.preventDefault();
      area.classList.remove("ativo");
      for (const arquivo of evento.dataTransfer.files) executar(arquivo);
    });
  }

  ligar($("#proteger"), $("#soltar-proteger"), proteger);
  ligar($("#restaurar"), $("#soltar-restaurar"), restaurar);
})();
