// Página do Véu: tudo roda aqui, no navegador. A política de segurança da página bloqueia conexões.
(() => {
  "use strict";
  const { Veu, Vault, LABELS, GROUPS, SECRET_LABELS } = window.veu;
  const $ = (id) => document.getElementById(id);
  const entrada = $("entrada");
  const saida = $("saida");
  const achados = $("achados");
  const resposta = $("resposta");
  const restaurado = $("restaurado");
  const operador = $("operador");
  const CHAVE = "veu-cofre";

  // Idioma: ?lang=pt|en, a escolha salva ou o idioma do navegador (português se algum for pt).
  function idiomaInicial() {
    const pedido = new URLSearchParams(location.search).get("lang");
    if (pedido === "pt" || pedido === "en") {
      try {
        localStorage.setItem("veu-idioma", pedido);
      } catch { /* sem armazenamento: vale só nesta visita */ }
      return pedido;
    }
    try {
      const salvo = localStorage.getItem("veu-idioma");
      if (salvo === "pt" || salvo === "en") return salvo;
    } catch { /* idem */ }
    const idiomas = navigator.languages?.length ? navigator.languages : [navigator.language || ""];
    return idiomas.some((idioma) => String(idioma).toLowerCase().startsWith("pt")) ? "pt" : "en";
  }
  const idioma = idiomaInicial();
  const T = window.veuTextos[idioma];
  document.documentElement.lang = idioma === "pt" ? "pt-BR" : "en";
  document.title = T.titulo;
  document.querySelector('meta[name="description"]')?.setAttribute("content", T.descricao);
  for (const elemento of document.querySelectorAll("[data-t]")) elemento.textContent = T[elemento.dataset.t];
  for (const elemento of document.querySelectorAll("[data-t-placeholder]")) elemento.placeholder = T[elemento.dataset.tPlaceholder];
  for (const elemento of document.querySelectorAll("[data-t-aria]")) elemento.setAttribute("aria-label", T[elemento.dataset.tAria]);
  for (const elemento of document.querySelectorAll("[data-t-href]")) elemento.href = T[elemento.dataset.tHref];
  $("idioma").href = `?lang=${idioma === "pt" ? "en" : "pt"}`;

  // Valores que a pessoa desmarcou (falsos positivos): não são escondidos.
  const ignorados = new Set();
  // Tipos que a pessoa desligou nas caixinhas de "O que esconder" (salvos neste navegador). Guardar os desligados,
  // e não os ligados, faz um tipo novo do Véu já chegar ligado.
  const CHAVE_TIPOS = "veu-tipos-desligados";
  const todosOsTipos = GROUPS.flatMap((grupo) => grupo.tipos);
  const desligados = new Set();
  try {
    for (const tipo of JSON.parse(localStorage.getItem(CHAVE_TIPOS) || "[]")) if (todosOsTipos.includes(tipo)) desligados.add(tipo);
  } catch { /* sem armazenamento: tudo ligado */ }
  const tiposLigados = () => todosOsTipos.filter((tipo) => !desligados.has(tipo));
  // Uma instância por configuração: montar as listas de nomes a cada tecla seria lento, e a mesma instância
  // reaproveita o cache de detecção de textos longos.
  const instancias = new Map();
  // Com o Véu Pro ativo nesta página, as listas próprias (nomes e termos que sempre somem) entram também.
  const termos = () => window.veuPro?.termos();
  function veuPara(lista, op) {
    const tipos = desligados.size ? tiposLigados() : undefined;
    const chave = JSON.stringify([lista, op, tipos, termos()]);
    if (!instancias.has(chave)) instancias.set(chave, new Veu({ allowlist: lista, operator: op, labels: tipos, terms: termos() }));
    return instancias.get(chave);
  }
  // Textos grandes vão para um trabalhador (Web Worker): a página continua respondendo.
  const GRANDE = 20000;
  let trabalhador = null;
  let pedido = 0;
  try {
    trabalhador = new Worker("trabalhador.js");
  } catch { /* sem suporte a Worker: tudo roda aqui mesmo */ }
  let cofre = carregarCofre();
  let rascunho = null;

  function carregarCofre() {
    try {
      const salvo = sessionStorage.getItem(CHAVE);
      if (salvo) return Vault.fromJSON(JSON.parse(salvo));
    } catch { /* aba anônima ou armazenamento bloqueado: segue só na memória */ }
    return new Vault();
  }

  function salvarCofre() {
    try {
      sessionStorage.setItem(CHAVE, JSON.stringify(cofre));
    } catch { /* idem */ }
  }

  const normalizar = (texto) => texto.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().trim();
  const nomeDoTipo = (rotulo) => (idioma === "en" ? window.veuTextos.rotulosEn[rotulo] : null)
    || (LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, "");

  function avisar(mensagem) {
    const aviso = $("aviso");
    aviso.textContent = mensagem;
    aviso.classList.add("visivel");
    clearTimeout(avisar.tempo);
    avisar.tempo = setTimeout(() => aviso.classList.remove("visivel"), 2600);
  }

  async function copiar(texto) {
    if (!texto) {
      avisar(T.nadaParaCopiar);
      return false;
    }
    try {
      await navigator.clipboard.writeText(texto);
    } catch {
      const area = document.createElement("textarea");
      area.value = texto;
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    return true;
  }

  /** Escreve o texto destacando os marcadores, sem nunca interpretar HTML. */
  function mostrarComMarcadores(elemento, texto) {
    elemento.replaceChildren();
    const marcador = /\[[A-Z]+(?:_[A-Z]+)*(?:_[0-9a-f]+)?\]|\*{2,}[^\s]*/g;
    let posicao = 0;
    for (const achado of texto.matchAll(marcador)) {
      elemento.append(texto.slice(posicao, achado.index));
      const marca = document.createElement("mark");
      marca.textContent = achado[0];
      elemento.append(marca);
      posicao = achado.index + achado[0].length;
    }
    elemento.append(texto.slice(posicao));
  }

  function mostrarAchados(entidades) {
    achados.replaceChildren();
    const unicos = new Map();
    for (const entidade of entidades) {
      const chave = `${entidade.label}|${normalizar(entidade.text)}`;
      if (!unicos.has(chave)) unicos.set(chave, entidade);
    }
    const resumo = document.createElement("span");
    resumo.className = "resumo";
    const protegidos = [...unicos.values()].filter((e) => !ignorados.has(normalizar(e.text))).length;
    resumo.textContent = unicos.size ? T.resumo(protegidos, unicos.size) : entrada.value.trim() ? T.nenhum : "";
    achados.append(resumo);
    for (const entidade of unicos.values()) {
      const chave = normalizar(entidade.text);
      const rotulo = document.createElement("label");
      rotulo.className = `achado${ignorados.has(chave) ? " solto" : ""}`;
      const caixa = document.createElement("input");
      caixa.type = "checkbox";
      caixa.checked = !ignorados.has(chave);
      caixa.addEventListener("change", () => {
        if (caixa.checked) ignorados.delete(chave);
        else ignorados.add(chave);
        atualizar();
      });
      const tipo = document.createElement("span");
      tipo.className = "tipo";
      tipo.textContent = nomeDoTipo(entidade.label);
      const valor = document.createElement("span");
      valor.textContent = entidade.text.length > 40 ? `${entidade.text.slice(0, 37)}...` : entidade.text;
      rotulo.append(caixa, tipo, valor);
      achados.append(rotulo);
    }
  }

  // Caixinhas de "O que esconder": uma por grupo e, dentro de cada grupo, uma por tipo.
  function montarTipos() {
    const lugar = $("tipos-grupos");
    lugar.replaceChildren();
    for (const grupo of GROUPS) {
      const bloco = document.createElement("div");
      bloco.className = "grupo";
      const rotulo = document.createElement("label");
      const caixa = document.createElement("input");
      caixa.type = "checkbox";
      caixa.id = `grupo-${grupo.id}`;
      const ligados = grupo.tipos.filter((tipo) => !desligados.has(tipo)).length;
      caixa.checked = ligados === grupo.tipos.length;
      caixa.indeterminate = ligados > 0 && ligados < grupo.tipos.length;
      caixa.addEventListener("change", () => mudarTipos(grupo.tipos, caixa.checked));
      const titulo = document.createElement("b");
      titulo.textContent = idioma === "en" ? grupo.titulo_en : grupo.titulo;
      const exemplo = document.createElement("span");
      exemplo.className = "exemplo";
      exemplo.textContent = idioma === "en" ? grupo.exemplo_en : grupo.exemplo;
      rotulo.append(caixa, titulo, exemplo);
      const detalhe = document.createElement("details");
      detalhe.open = caixa.indeterminate;
      const resumo = document.createElement("summary");
      resumo.textContent = T.umAUm;
      const lista = document.createElement("div");
      lista.className = "um-a-um";
      for (const tipo of grupo.tipos) {
        const item = document.createElement("label");
        const caixaDoTipo = document.createElement("input");
        caixaDoTipo.type = "checkbox";
        caixaDoTipo.id = `tipo-${tipo}`;
        caixaDoTipo.checked = !desligados.has(tipo);
        caixaDoTipo.addEventListener("change", () => mudarTipos([tipo], caixaDoTipo.checked));
        item.append(caixaDoTipo, nomeDoTipo(tipo));
        lista.append(item);
      }
      detalhe.append(resumo, lista);
      bloco.append(rotulo, detalhe);
      lugar.append(bloco);
    }
    const gruposInteiros = GROUPS.filter((grupo) => grupo.tipos.every((tipo) => !desligados.has(tipo))).length;
    $("tipos-resumo").textContent = desligados.size ? T.tiposAlguns(gruposInteiros, GROUPS.length) : T.tiposTudo;
  }

  function mudarTipos(tipos, ligar) {
    for (const tipo of tipos) {
      if (ligar) desligados.delete(tipo);
      else desligados.add(tipo);
    }
    try {
      localStorage.setItem(CHAVE_TIPOS, JSON.stringify([...desligados]));
    } catch { /* sem armazenamento: vale só nesta visita */ }
    // Desligar senhas e chaves é o erro mais caro: a pessoa precisa saber o que acontece.
    if (!ligar && tipos.some((tipo) => SECRET_LABELS.has(tipo))) avisar(T.avisoSegredos);
    montarTipos();
    atualizar();
  }

  function atualizar() {
    const texto = entrada.value;
    if (!texto) {
      mostrarAchados([]);
      rascunho = null;
      saida.replaceChildren();
      return;
    }
    if (!tiposLigados().length) { // nada marcado: o texto segue como está
      pedido += 1;
      mostrarAchados([]);
      rascunho = { texto, cofre: Vault.fromJSON(cofre.toJSON()) };
      saida.textContent = texto;
      return;
    }
    if (trabalhador && texto.length >= GRANDE) {
      // A prévia usa uma cópia do cofre: a numeração continua a da conversa ([CPF_2] depois de [CPF_1]).
      const id = ++pedido;
      saida.textContent = T.analisando;
      trabalhador.onmessage = ({ data }) => {
        if (data.id !== pedido) return; // chegou uma versão mais nova do texto
        if (data.erro) return avisar(T.erroAnalise);
        mostrarAchados(data.entidades);
        rascunho = { texto: data.texto, cofre: Vault.fromJSON(data.cofre) };
        mostrarComMarcadores(saida, data.texto);
      };
      trabalhador.postMessage({ id, texto, ignorar: [...ignorados], operador: operador.value, cofre: cofre.toJSON(),
        tipos: desligados.size ? tiposLigados() : undefined, termos: termos() });
      return;
    }
    pedido += 1; // descarta respostas atrasadas do trabalhador
    mostrarAchados(veuPara([], "token").analyze(texto));
    const copia = Vault.fromJSON(cofre.toJSON());
    const resultado = veuPara([...ignorados], operador.value).anonymize(texto, copia);
    rascunho = { texto: resultado.text, cofre: copia };
    mostrarComMarcadores(saida, resultado.text);
  }

  function restaurar() {
    const texto = resposta.value;
    restaurado.textContent = texto ? cofre.restore(texto) : "";
  }

  let espera;
  entrada.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(atualizar, 120);
  });
  operador.addEventListener("change", atualizar);
  resposta.addEventListener("input", restaurar);

  $("copiar-protegido").addEventListener("click", async () => {
    if (!rascunho) return avisar(T.colePrimeiro);
    cofre = rascunho.cofre;
    salvarCofre();
    if (await copiar(rascunho.texto)) avisar(T.copiado);
    restaurar();
  });

  $("copiar-restaurado").addEventListener("click", async () => {
    restaurar();
    if (await copiar(restaurado.textContent)) avisar(T.respostaCopiada);
  });

  $("limpar").addEventListener("click", () => {
    entrada.value = "";
    resposta.value = "";
    ignorados.clear();
    cofre = new Vault();
    try {
      sessionStorage.removeItem(CHAVE);
    } catch { /* nada a apagar */ }
    atualizar();
    restaurar();
    avisar(T.apagado);
  });

  $("arquivo").addEventListener("change", (evento) => {
    const arquivo = evento.target.files[0];
    if (!arquivo) return;
    if (arquivo.size > 5 * 1024 * 1024) return avisar(T.arquivoGrande);
    const leitor = new FileReader();
    leitor.onload = () => {
      entrada.value = String(leitor.result);
      atualizar();
      avisar(T.arquivoAberto(arquivo.name));
    };
    leitor.readAsText(arquivo, "utf-8");
    evento.target.value = "";
  });

  // Para a parte de arquivos (arquivos.js): o mesmo cofre, então a resposta da IA sobre um arquivo também volta
  // com os dados reais no passo 3.
  window.veuPagina = {
    T, idioma, avisar,
    cofre: () => Vault.fromJSON(cofre.toJSON()),
    guardar(novo) {
      cofre = novo;
      salvarCofre();
      atualizar();
      restaurar();
    },
    veu: () => veuPara([...ignorados], "token"),
    nomeDoTipo,
  };
  window.veuPro?.aoMudar(() => {
    instancias.clear();
    atualizar();
  });

  montarTipos();
  atualizar();
  restaurar();
})();
