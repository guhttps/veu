// Arquivos inteiros na página: Word, Excel e PowerPoint voltam no mesmo formato, PDF vira texto. Tudo no navegador;
// o PDF é lido pelo pdf.js servido por este mesmo site. Grátis: um arquivo por vez, até 10 MB. Véu Pro: vários de
// uma vez e até 100 MB. O cofre é o mesmo da caixa de texto, então a resposta da IA volta com os dados reais no passo 3.
(() => {
  "use strict";
  const { protectDocument, restoreDocument, documentKind } = window.veu;
  const pagina = window.veuPagina;
  const pro = window.veuPro;
  const T = pagina.T;
  const $ = (id) => document.getElementById(id);
  const MB = 1024 * 1024;
  const TEXTO = new Set(["txt", "md", "csv", "tsv", "json", "jsonl", "log", "xml", "html", "yml", "yaml", "ini", "sql"]);
  const limite = () => (pro.estado.ativo ? 100 : 10) * MB;

  const extensao = (nome) => nome.toLowerCase().split(".").pop();
  const base = (nome) => nome.replace(/\.[^.]+$/, "");
  // "Nome de pessoa" vira "nome de pessoa", mas siglas como CPF e IBAN ficam em maiúsculas.
  const minuscula = (nome) => (/^\p{Lu}[\p{Ll}-]/u.test(nome) ? nome[0].toLowerCase() + nome.slice(1) : nome);
  const resumo = (contagem) => Object.entries(contagem)
    .map(([rotulo, n]) => `${n} ${minuscula(pagina.nomeDoTipo(rotulo))}`).join(", ");

  async function textoDoPdf(bytes) {
    const pdfjs = await import(new URL("pdf.min.mjs", location.href).href);
    pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdf.worker.min.mjs", location.href).href;
    const documento = await pdfjs.getDocument({ data: bytes, isEvalSupported: false }).promise;
    const paginas = [];
    for (let numero = 1; numero <= documento.numPages; numero++) {
      const conteudo = await (await documento.getPage(numero)).getTextContent();
      const texto = conteudo.items.map((item) => item.str + (item.hasEOL ? "\n" : "")).join("").trim();
      if (texto) paginas.push(`## ${T.paginaDoPdf} ${numero}\n\n${texto}`);
    }
    return paginas.join("\n\n");
  }

  function baixar(bytes, nome, tipo) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([bytes], { type: tipo || "application/octet-stream" }));
    link.download = nome;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  }

  function registrar(texto, erro = false) {
    const linha = document.createElement("li");
    linha.textContent = texto;
    if (erro) linha.className = "erro";
    $("arquivos-feitos").prepend(linha);
  }

  // Prints e fotos (Véu Pro): tarja preta sobre os dados e os QR Codes; a imagem volta como PNG.
  async function protegerImagem(arquivo) {
    if (!pro.estado.ativo) {
      pagina.avisar(T.imagemSoPro(arquivo.name));
      return registrar(T.imagemSoPro(arquivo.name), true);
    }
    registrar(T.imagemLendo(arquivo.name));
    const veu = pagina.veu();
    const { blob, counts } = await window.veuImagens.proteger(arquivo, (texto) => veu.analyze(texto), pagina.ligado);
    const nome = `${base(arquivo.name)}-protegido.png`;
    baixar(blob, nome, "image/png");
    registrar(Object.keys(counts).length ? T.arquivoProtegido(nome, resumo(counts)) : T.arquivoSemDados(nome));
  }

  async function proteger(arquivo) {
    const tipo = extensao(arquivo.name);
    const tipoDocumento = documentKind(arquivo.name);
    if (window.veuImagens?.ehImagem(arquivo.name)) return protegerImagem(arquivo);
    if (!tipoDocumento && tipo !== "pdf" && !TEXTO.has(tipo)) return registrar(T.arquivoTipo(arquivo.name), true);
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    const vault = pagina.cofre();
    const veu = pagina.veu();
    let saida;
    let contagem;
    let nome;
    if (tipoDocumento) {
      ({ bytes: saida, counts: contagem } = await protectDocument(bytes, tipoDocumento, veu, vault));
      nome = `${base(arquivo.name)}-protegido.${tipo}`;
    } else {
      const texto = tipo === "pdf" ? await textoDoPdf(bytes) : new TextDecoder().decode(bytes);
      const resultado = veu.anonymize(texto, vault);
      contagem = resultado.counts();
      saida = new TextEncoder().encode(resultado.text);
      nome = `${base(arquivo.name)}-protegido.${tipo === "pdf" ? "txt" : tipo}`;
    }
    pagina.guardar(vault);
    baixar(saida, nome, tipo === "pdf" ? "text/plain" : arquivo.type);
    registrar(Object.keys(contagem).length ? T.arquivoProtegido(nome, resumo(contagem)) : T.arquivoSemDados(nome));
  }

  async function devolver(arquivo) {
    const tipo = extensao(arquivo.name);
    const tipoDocumento = documentKind(arquivo.name);
    const vault = pagina.cofre();
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    let saida;
    if (tipoDocumento) saida = await restoreDocument(bytes, tipoDocumento, vault);
    else if (TEXTO.has(tipo)) saida = new TextEncoder().encode(vault.restore(new TextDecoder().decode(bytes)));
    else return registrar(T.arquivoDevolverTipo(arquivo.name), true);
    const nome = `${base(arquivo.name).replace(/-protegido$/, "")}-com-dados.${tipo}`;
    baixar(saida, nome, arquivo.type);
    registrar(T.arquivoDevolvido(nome));
  }

  /** Um arquivo por vez no grátis; vários com o Véu Pro. Cada um passa pelo limite de tamanho. */
  async function receber(lista, acao) {
    let arquivos = [...lista];
    if (arquivos.length > 1 && !pro.estado.ativo) {
      pagina.avisar(T.variosSoPro);
      registrar(T.variosSoPro, true);
      arquivos = arquivos.slice(0, 1);
    }
    for (const arquivo of arquivos) {
      if (arquivo.size > limite()) {
        registrar(pro.estado.ativo ? T.arquivoGrandePro(arquivo.name) : T.arquivoGrandeGratis(arquivo.name), true);
        continue;
      }
      try {
        await acao(arquivo);
      } catch (erro) {
        registrar(`${arquivo.name}: ${erro?.message || T.arquivoErro}`, true);
      }
    }
  }

  function ligar(entrada, area, acao) {
    entrada.addEventListener("change", async () => {
      const lista = [...entrada.files];
      entrada.value = "";
      await receber(lista, acao);
    });
    area.addEventListener("dragover", (evento) => { evento.preventDefault(); area.classList.add("ativo"); });
    area.addEventListener("dragleave", () => area.classList.remove("ativo"));
    area.addEventListener("drop", (evento) => {
      evento.preventDefault();
      area.classList.remove("ativo");
      receber(evento.dataTransfer.files, acao);
    });
  }

  ligar($("arquivo-proteger"), $("soltar-proteger"), proteger);
  ligar($("arquivo-devolver"), $("soltar-devolver"), devolver);

  // Véu Pro nesta página: ativar a chave, as listas próprias e o que muda nos arquivos.
  const data = (segundos) => new Date(segundos * 1000).toLocaleDateString(pagina.idioma === "pt" ? "pt-BR" : "en");
  function mostrarPro(estado) {
    const ativo = estado.ativo;
    $("arquivo-proteger").multiple = ativo;
    $("arquivo-devolver").multiple = ativo;
    $("arquivos-limite").textContent = ativo ? T.limitePro : T.limiteGratis;
    $("pro-estado").textContent = ativo ? T.proAtivo(data(estado.exp), estado.email)
      : estado.motivo === "vencida" ? T.proVencida(data(estado.exp)) : T.proConvite;
    $("pro-ativar").hidden = ativo;
    $("pro-ativo").hidden = !ativo;
    $("pro-resumo").textContent = ativo ? T.proResumoAtivo : T.proResumo;
    $("lista-nomes").value = estado.listaNomes.join("\n");
    $("lista-termos").value = estado.listaTermos.join("\n");
  }
  pro.aoMudar(mostrarPro);
  pro.pronto.then(mostrarPro);

  const MOTIVOS = { formato: T.proFormato, assinatura: T.proAssinatura, "sem-chave-publica": T.proFormato };
  $("pro-botao").addEventListener("click", async () => {
    const resultado = await pro.ativar($("pro-chave").value);
    if (resultado.ok) {
      $("pro-chave").value = "";
      pagina.avisar(T.proAtivado);
    } else {
      $("pro-estado").textContent = resultado.motivo === "vencida" ? T.proVencida(data(resultado.exp)) : MOTIVOS[resultado.motivo] || T.proFormato;
    }
  });
  $("pro-remover").addEventListener("click", () => pro.remover());
  $("salvar-listas").addEventListener("click", async () => {
    const linhas = (id) => $(id).value.split("\n").map((linha) => linha.trim()).filter(Boolean);
    await pro.salvarListas(linhas("lista-nomes"), linhas("lista-termos"));
    pagina.avisar(T.listasSalvas);
  });
})();
