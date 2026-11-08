// Página do Véu: tudo roda aqui, no navegador. A política de segurança da página bloqueia conexões.
(() => {
  "use strict";
  const { Veu, Vault, LABELS } = window.veu;
  const $ = (id) => document.getElementById(id);
  const entrada = $("entrada");
  const saida = $("saida");
  const achados = $("achados");
  const resposta = $("resposta");
  const restaurado = $("restaurado");
  const operador = $("operador");
  const CHAVE = "veu-cofre";

  // Valores que a pessoa desmarcou (falsos positivos): não são escondidos.
  const ignorados = new Set();
  const base = new Veu();
  // Uma instância por configuração: montar as listas de nomes a cada tecla seria lento, e a mesma instância
  // reaproveita o cache de detecção de textos longos.
  const instancias = new Map();
  function veuPara(lista, op) {
    const chave = JSON.stringify([lista, op]);
    if (!instancias.has(chave)) instancias.set(chave, new Veu({ allowlist: lista, operator: op }));
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
  const nomeDoTipo = (rotulo) => (LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, "");

  function avisar(mensagem) {
    const aviso = $("aviso");
    aviso.textContent = mensagem;
    aviso.classList.add("visivel");
    clearTimeout(avisar.tempo);
    avisar.tempo = setTimeout(() => aviso.classList.remove("visivel"), 2600);
  }

  async function copiar(texto) {
    if (!texto) {
      avisar("Nada para copiar ainda.");
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
    resumo.textContent = unicos.size
      ? `${protegidos} de ${unicos.size} ${unicos.size === 1 ? "dado será escondido" : "dados serão escondidos"}. Desmarque o que não for dado pessoal.`
      : entrada.value.trim() ? "Nenhum dado pessoal encontrado." : "";
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

  function atualizar() {
    const texto = entrada.value;
    if (!texto) {
      mostrarAchados([]);
      rascunho = null;
      saida.replaceChildren();
      return;
    }
    if (trabalhador && texto.length >= GRANDE) {
      // A prévia usa uma cópia do cofre: a numeração continua a da conversa ([CPF_2] depois de [CPF_1]).
      const id = ++pedido;
      saida.textContent = "Analisando o texto...";
      trabalhador.onmessage = ({ data }) => {
        if (data.id !== pedido) return; // chegou uma versão mais nova do texto
        if (data.erro) return avisar("Não consegui analisar este texto.");
        mostrarAchados(data.entidades);
        rascunho = { texto: data.texto, cofre: Vault.fromJSON(data.cofre) };
        mostrarComMarcadores(saida, data.texto);
      };
      trabalhador.postMessage({ id, texto, ignorar: [...ignorados], operador: operador.value, cofre: cofre.toJSON() });
      return;
    }
    pedido += 1; // descarta respostas atrasadas do trabalhador
    mostrarAchados(base.analyze(texto));
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
    if (!rascunho) return avisar("Cole ou digite um texto primeiro.");
    cofre = rascunho.cofre;
    salvarCofre();
    if (await copiar(rascunho.texto)) avisar("Copiado. Cole na IA e depois traga a resposta para o passo 3.");
    restaurar();
  });

  $("copiar-restaurado").addEventListener("click", async () => {
    restaurar();
    if (await copiar(restaurado.textContent)) avisar("Resposta copiada com os dados reais.");
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
    avisar("Tudo apagado.");
  });

  $("arquivo").addEventListener("change", (evento) => {
    const arquivo = evento.target.files[0];
    if (!arquivo) return;
    if (arquivo.size > 5 * 1024 * 1024) return avisar("Arquivo grande demais (máximo de 5 MB).");
    const leitor = new FileReader();
    leitor.onload = () => {
      entrada.value = String(leitor.result);
      atualizar();
      avisar(`"${arquivo.name}" aberto. Ele não sai do seu computador.`);
    };
    leitor.readAsText(arquivo, "utf-8");
    evento.target.value = "";
  });

  atualizar();
  restaurar();
})();
