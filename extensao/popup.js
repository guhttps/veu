"use strict";
(async () => {
  const $ = (seletor) => document.querySelector(seletor);
  const { LABELS } = window.veu;
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
