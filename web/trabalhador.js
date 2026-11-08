// Trabalhador da página do Véu: analisa textos grandes fora da tela, para a página não travar.
// Também roda só no navegador; a página e este arquivo vêm do mesmo endereço e não fazem conexões.
/* global importScripts */
"use strict";
importScripts("veu.global.js");

const instancias = new Map();

function veuPara(ignorar, operador) {
  const chave = JSON.stringify([ignorar, operador]);
  let veu = instancias.get(chave);
  if (!veu) {
    veu = new self.veu.Veu({ allowlist: ignorar, operator: operador });
    instancias.set(chave, veu);
  }
  return veu;
}

self.onmessage = ({ data }) => {
  const { id, texto, ignorar, operador, cofre } = data;
  try {
    const entidades = veuPara([], "token").analyze(texto).map(({ label, start, end, text }) => ({ label, start, end, text }));
    const copia = self.veu.Vault.fromJSON(cofre);
    const resultado = veuPara(ignorar, operador).anonymize(texto, copia);
    self.postMessage({ id, entidades, texto: resultado.text, cofre: copia.toJSON() });
  } catch (erro) {
    self.postMessage({ id, erro: String(erro) });
  }
};
