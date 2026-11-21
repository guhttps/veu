"use strict";
(async () => {
  const $ = (seletor) => document.querySelector(seletor);
  const { LABELS, GROUPS, SECRET_LABELS } = window.veu;
  const [aba] = await chrome.tabs.query({ active: true, currentWindow: true });
  let config = await chrome.runtime.sendMessage({ tipo: "configuracao" });

  function mostrar() {
    const travado = (campo) => config.travarConfiguracao || config.camposDaEmpresa.includes(campo);
    $("#empresa").hidden = !config.gerenciada;
    $("#ativo").checked = config.ativo;
    $("#ativo").disabled = travado("ativo");
    for (const opcao of document.querySelectorAll("input[name=modo]")) {
      opcao.checked = opcao.value === config.modo;
      opcao.disabled = travado("modo");
    }
    $("#restaurar-respostas").checked = config.restaurarRespostas;
    $("#restaurar-respostas").disabled = travado("restaurarRespostas");
    mostrarGrupos(travado("tiposDesligados") || travado("tipos"));
    mostrarPro(travado);
  }

  // Véu Pro: a chave confere a assinatura; as listas próprias só valem com ela.
  function mostrarPro(travado) {
    const pro = config.pro || { ativo: false };
    const validade = pro.exp ? new Date(pro.exp * 1000).toLocaleDateString("pt-BR") : "";
    const plano = pro.plano === "empresa" ? "Véu Empresa" : "Véu Pro";
    // Chave paga por período (Pix, boleto): não renova sozinha, então avisamos perto do fim.
    const fimDoPeriodo = pro.avulsa && !pro.daEmpresa && (pro.acabando || pro.motivo === "vencida");
    $("#pro-estado").textContent = pro.ativo
      ? `${plano} ativo até ${validade}${pro.email ? ` (${pro.email})` : ""}${pro.daEmpresa ? ", pela sua empresa" : ""}.`
        + (fimDoPeriodo ? " O período pago está acabando: para continuar, pague mais um período." : "")
      : pro.motivo === "vencida" && pro.avulsa ? `O período pago terminou em ${validade}. Para continuar, pague mais um período.`
      : pro.motivo === "vencida" ? `A chave venceu em ${validade}. Se a assinatura está ativa, o Véu renova sozinho.`
      : "Sem chave neste navegador. Com o Pro, você cria listas de nomes e termos que sempre somem.";
    // Pagar mais um período a qualquer hora: o preço guardado na chave vale, e os dias que faltam são somados.
    $("#pro-pagar").hidden = !pro.avulsa || pro.daEmpresa;
    const preco = (centavos) => (Number.isInteger(centavos) ? ` (R$ ${(centavos / 100).toFixed(2).replace(".", ",")})` : "");
    $("#pagar-mensal").textContent = `Pagar mais 1 mês${preco(pro.precos?.mensal)}`;
    $("#pagar-anual").textContent = `Pagar mais 1 ano${preco(pro.precos?.anual)}`;
    $("#pro-ativar").hidden = pro.ativo || pro.daEmpresa;
    $("#pro-remover").hidden = !pro.exp || pro.daEmpresa;
    $("#pro-cancelar").hidden = !pro.assinatura || pro.daEmpresa;
    $("#pro-listas").hidden = !pro.ativo;
    $("#pro-paginas").hidden = !pro.ativo;
    $("#lista-nomes").value = (config.listaNomes || []).join("\n");
    $("#lista-termos").value = (config.listaTermos || []).join("\n");
    $("#lista-nomes").disabled = travado("listaNomes");
    $("#lista-termos").disabled = travado("listaTermos");
  }

  async function pedir(mensagem) {
    const resposta = await chrome.runtime.sendMessage(mensagem);
    if (resposta?.erro) {
      $("#pro-estado").textContent = resposta.erro;
      return false;
    }
    config = resposta;
    mostrar();
    if (aba?.id) chrome.tabs.sendMessage(aba.id, { tipo: "recarregar" }).catch(() => {});
    return true;
  }

  // No Firefox, a renovação manda a chave (com o e-mail da assinatura) ao servidor de licenças: a pessoa autoriza.
  async function permitirRenovacao() {
    const permissoes = globalThis.browser?.permissions;
    if (!permissoes?.request || !/Firefox\//.test(navigator.userAgent)) return true;
    try {
      return await permissoes.request({ data_collection: ["authenticationInfo", "personallyIdentifyingInfo"] });
    } catch {
      return true;
    }
  }

  $("#pro-botao").addEventListener("click", async () => {
    if (!(await permitirRenovacao())) {
      $("#pro-estado").textContent = "Sem a permissão, a chave não renova sozinha: ela vale até o vencimento.";
    }
    if (await pedir({ tipo: "ativarLicenca", chave: $("#pro-chave").value })) $("#pro-chave").value = "";
  });
  $("#pro-remover").addEventListener("click", () => pedir({ tipo: "removerLicenca" }));
  // Cancelar a assinatura pede dois cliques: o primeiro só troca o texto do botão por uma confirmação.
  let confirmarCancelamento = false;
  $("#pro-cancelar").addEventListener("click", async () => {
    const botao = $("#pro-cancelar");
    if (!confirmarCancelamento) {
      confirmarCancelamento = true;
      botao.textContent = "Confirmar: cancelar a assinatura";
      setTimeout(() => { confirmarCancelamento = false; botao.textContent = "Cancelar a assinatura"; }, 6000);
      return;
    }
    confirmarCancelamento = false;
    if (!(await permitirRenovacao())) {
      $("#pro-estado").textContent = "Sem a permissão, cancele em licencas.veu-pro.workers.dev/cancelar.";
      return;
    }
    $("#pro-estado").textContent = "Cancelando...";
    const resposta = await chrome.runtime.sendMessage({ tipo: "cancelarAssinatura" });
    $("#pro-estado").textContent = resposta?.erro || resposta?.mensagem || "Pronto.";
    botao.textContent = "Cancelar a assinatura";
  });
  for (const periodo of ["mensal", "anual"]) {
    $(`#pagar-${periodo}`).addEventListener("click", async () => {
      if (!(await permitirRenovacao())) {
        $("#pro-estado").textContent = "Sem a permissão, o Véu não consegue abrir o pagamento pelo seu preço.";
        return;
      }
      $("#pro-estado").textContent = "Abrindo o pagamento...";
      const resposta = await chrome.runtime.sendMessage({ tipo: "pagarPeriodo", periodo });
      $("#pro-estado").textContent = resposta?.erro || (resposta?.precoMantido
        ? "O pagamento abriu numa aba nova, com o seu preço de sempre." : "O pagamento abriu numa aba nova.");
    });
  }
  // Arquivos usa o cofre da aba aberta: as respostas da IA nessa aba também voltam com os dados reais.
  $("#abrir-arquivos").addEventListener("click", () => {
    let site = "";
    try {
      site = aba?.url ? new URL(aba.url).hostname : "";
    } catch { /* aba sem endereço */ }
    const pagina = aba?.id && /^https?:/.test(aba.url || "") ? `arquivos.html?aba=${aba.id}&site=${encodeURIComponent(site)}` : "arquivos.html";
    chrome.tabs.create({ url: chrome.runtime.getURL(pagina) });
  });
  $("#abrir-relatorio").addEventListener("click", () => chrome.tabs.create({ url: chrome.runtime.getURL("relatorio.html") }));
  $("#salvar-listas").addEventListener("click", async () => {
    const linhas = (campo) => $(campo).value.split("\n").map((linha) => linha.trim()).filter(Boolean);
    if (await pedir({ tipo: "salvarListas", listaNomes: linhas("#lista-nomes"), listaTermos: linhas("#lista-termos") })) {
      $("#pro-estado").textContent = "Listas salvas.";
    }
  });

  // Caixinhas por grupo (os mesmos grupos da página e do painel). A empresa pode travar a escolha.
  function mostrarGrupos(travadas) {
    const desligados = new Set(config.tiposDesligados || []);
    const permitidos = config.tipos?.length ? new Set(config.tipos) : null;
    const lugar = $("#grupos");
    lugar.replaceChildren();
    for (const grupo of GROUPS) {
      const tipos = grupo.tipos.filter((tipo) => !permitidos || permitidos.has(tipo));
      if (!tipos.length) continue;
      const rotulo = document.createElement("label");
      const caixa = document.createElement("input");
      caixa.type = "checkbox";
      caixa.id = `grupo-${grupo.id}`;
      const ligados = tipos.filter((tipo) => !desligados.has(tipo)).length;
      caixa.checked = ligados === tipos.length;
      caixa.indeterminate = ligados > 0 && ligados < tipos.length;
      caixa.disabled = travadas;
      caixa.addEventListener("change", () => {
        const novos = new Set(config.tiposDesligados || []);
        for (const tipo of tipos) {
          if (caixa.checked) novos.delete(tipo);
          else novos.add(tipo);
        }
        $("#aviso-tipos").textContent = !caixa.checked && tipos.some((tipo) => SECRET_LABELS.has(tipo))
          ? "Atenção: com senhas e chaves desmarcadas, a IA vai ver esses valores." : "";
        salvar({ tiposDesligados: [...novos] });
      });
      const titulo = document.createElement("b");
      titulo.textContent = grupo.titulo;
      const exemplo = document.createElement("span");
      exemplo.className = "exemplo";
      exemplo.textContent = grupo.exemplo;
      rotulo.append(caixa, titulo, exemplo);
      lugar.append(rotulo);
    }
  }

  async function salvar(preferencias) {
    const resposta = await chrome.runtime.sendMessage({ tipo: "salvarPreferencias", preferencias });
    if (resposta?.erro) $("#resultado").textContent = resposta.erro;
    else config = resposta;
    mostrar();
    if (aba?.id) chrome.tabs.sendMessage(aba.id, { tipo: "recarregar" }).catch(() => {});
  }

  $("#ativo").addEventListener("change", (e) => salvar({ ativo: e.target.checked }));
  $("#restaurar-respostas").addEventListener("change", (e) => salvar({ restaurarRespostas: e.target.checked }));
  for (const opcao of document.querySelectorAll("input[name=modo]")) {
    opcao.addEventListener("change", () => salvar({ modo: opcao.value }));
  }

  if (aba?.id) {
    const contagem = await chrome.runtime.sendMessage({ tipo: "contagem", abaId: aba.id });
    const partes = Object.entries(contagem || {}).map(([rotulo, n]) => `${n} ${(LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, "")}`);
    if (partes.length) $("#contagem").textContent = `Protegidos: ${partes.join(", ")}.`;
  }

  $("#restaurar").addEventListener("click", async () => {
    const texto = $("#texto").value;
    if (!texto || !aba?.id) return;
    try {
      const resposta = await chrome.tabs.sendMessage(aba.id, { tipo: "restaurar", texto });
      await navigator.clipboard.writeText(resposta.texto);
      $("#resultado").textContent = resposta.texto === texto
        ? "Nenhum marcador desta aba encontrado no texto."
        : "Copiado com os dados reais.";
    } catch {
      $("#resultado").textContent = "Abra a aba da IA onde os dados foram protegidos.";
    }
  });

  mostrar();
})();
