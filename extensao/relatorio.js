"use strict";
// Relatório mensal do Véu Pro: lê as contagens guardadas pelo service worker (só números) e monta a página.
(async () => {
  const $ = (seletor) => document.querySelector(seletor);
  const { LABELS, GROUPS } = window.veu;
  const grupoDe = Object.fromEntries(GROUPS.flatMap((grupo) => grupo.tipos.map((tipo) => [tipo, grupo.titulo])));
  const nomeDoTipo = (rotulo) => (LABELS[rotulo] || rotulo).replace(/ \(.*\)$/, "");
  const nomeDoMes = (chave) => {
    const [ano, mes] = chave.split("-").map(Number);
    return new Date(ano, mes - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  };
  const numero = (n) => n.toLocaleString("pt-BR");
  let dados = await chrome.runtime.sendMessage({ tipo: "relatorio" });

  function linha(celulas) {
    const tr = document.createElement("tr");
    for (const [texto, classe] of celulas) {
      const td = document.createElement("td");
      td.textContent = texto;
      if (classe) td.className = classe;
      tr.append(td);
    }
    return tr;
  }

  function ordenado(objeto) {
    return Object.entries(objeto || {}).sort((a, b) => b[1] - a[1]);
  }

  function mostrar(chave) {
    const mes = dados.meses[chave] || { tipos: {}, sites: {}, dias: {}, envios: 0 };
    const total = Object.values(mes.tipos).reduce((soma, n) => soma + n, 0);
    $("#titulo").textContent = `Relatório de ${nomeDoMes(chave)}`;
    $("#total").textContent = numero(total);
    $("#envios").textContent = numero(mes.envios || 0);
    $("#qtd-tipos").textContent = numero(Object.keys(mes.tipos).length);
    $("#qtd-sites").textContent = numero(Object.keys(mes.sites).length);
    $("#tipos").replaceChildren(...ordenado(mes.tipos).map(([rotulo, n]) =>
      linha([[nomeDoTipo(rotulo)], [grupoDe[rotulo] || ""], [numero(n), "n"]])));
    $("#sites").replaceChildren(...ordenado(mes.sites).map(([site, n]) => linha([[site], [numero(n), "n"]])));
    const [ano, numeroDoMes] = chave.split("-").map(Number);
    const diasNoMes = new Date(ano, numeroDoMes, 0).getDate();
    const maior = Math.max(1, ...Object.values(mes.dias));
    $("#dias").replaceChildren(...Array.from({ length: diasNoMes }, (_, i) => {
      const barra = document.createElement("div");
      const n = mes.dias[String(i + 1)] || 0;
      barra.style.height = `${Math.round((n / maior) * 100)}%`;
      barra.title = `Dia ${i + 1}: ${numero(n)}`;
      return barra;
    }));
    $("#ultimo-dia").textContent = `dia ${diasNoMes}`;
  }

  function csv(chave) {
    const mes = dados.meses[chave] || { tipos: {}, sites: {} };
    const campo = (texto) => `"${String(texto).replace(/"/g, '""')}"`;
    const linhas = [["parte", "nome", "grupo", "escondidos"]];
    for (const [rotulo, n] of ordenado(mes.tipos)) linhas.push(["tipo", nomeDoTipo(rotulo), grupoDe[rotulo] || "", n]);
    for (const [site, n] of ordenado(mes.sites)) linhas.push(["site", site, "", n]);
    return "﻿" + linhas.map((celulas) => celulas.map(campo).join(";")).join("\r\n") + "\r\n";
  }

  function iniciar() {
    $("#sem-pro").hidden = Boolean(dados.pro?.ativo);
    $("#conteudo").hidden = !dados.pro?.ativo;
    if (!dados.pro?.ativo) return;
    const agora = new Date();
    const atual = `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}`;
    const meses = [...new Set([atual, ...Object.keys(dados.meses)])].sort().reverse();
    $("#mes").replaceChildren(...meses.map((chave) => new Option(nomeDoMes(chave), chave)));
    mostrar($("#mes").value);
  }

  $("#mes").addEventListener("change", () => mostrar($("#mes").value));
  $("#imprimir").addEventListener("click", () => window.print());
  $("#csv").addEventListener("click", () => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv($("#mes").value)], { type: "text/csv;charset=utf-8" }));
    link.download = `veu-relatorio-${$("#mes").value}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  });
  $("#apagar").addEventListener("click", async () => {
    if (!confirm("Apagar o histórico de todos os meses? Isso não pode ser desfeito.")) return;
    await chrome.runtime.sendMessage({ tipo: "apagarRelatorio" });
    dados = await chrome.runtime.sendMessage({ tipo: "relatorio" });
    iniciar();
  });
  iniciar();
})();
