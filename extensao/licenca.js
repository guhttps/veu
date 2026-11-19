// Licença do plano Pro: uma chave assinada (Ed25519) que a extensão confere sem internet.
// Formato: VEU1.<dados em base64url>.<assinatura em base64url>. Os dados têm o plano, o e-mail, a assinatura do
// Mercado Pago e a validade; nenhum texto da pessoa passa por aqui. Só a renovação fala com o servidor, mandando a
// própria chave. A chave pública e o endereço do servidor são definidos por nuvem/gerar-chaves.mjs.
"use strict";
(() => {
  const CHAVE_PUBLICA = "62O3t2ByV5o4dWL3VZNTl5mXWQjwOZm9ndF6hDB20U8"; // chave pública Ed25519 (base64url), de nuvem/gerar-chaves.mjs
  const SERVIDOR = "https://licencas.veu-pro.workers.dev"; // servidor de licenças (nuvem/worker.js)
  const PREFIXO = "VEU1.";

  function deBase64url(texto) {
    const base64 = texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4);
    return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  }

  /** Confere a chave: { valida, licenca, motivo }. motivo: formato, assinatura, vencida ou sem-chave-publica. */
  async function verificar(chave, chavePublica = CHAVE_PUBLICA, agora = Date.now()) {
    const texto = String(chave || "").trim();
    if (!chavePublica) return { valida: false, motivo: "sem-chave-publica" };
    const partes = texto.split(".");
    if (!texto.startsWith(PREFIXO) || partes.length !== 3) return { valida: false, motivo: "formato" };
    let licenca;
    try {
      const publica = await crypto.subtle.importKey("raw", deBase64url(chavePublica), { name: "Ed25519" }, false,
        ["verify"]);
      const assinada = new TextEncoder().encode(`${partes[0]}.${partes[1]}`);
      if (!(await crypto.subtle.verify({ name: "Ed25519" }, publica, deBase64url(partes[2]), assinada))) {
        return { valida: false, motivo: "assinatura" };
      }
      licenca = JSON.parse(new TextDecoder().decode(deBase64url(partes[1])));
    } catch {
      return { valida: false, motivo: "formato" };
    }
    if (licenca.v !== 1 || !["pro", "empresa"].includes(licenca.plano)) return { valida: false, motivo: "formato" };
    if (!(licenca.exp * 1000 > agora)) return { valida: false, licenca, motivo: "vencida" };
    return { valida: true, licenca };
  }

  /** Pede ao servidor uma chave nova enquanto a assinatura estiver ativa: { chave } ou { erro }. */
  async function renovar(chave, servidor = SERVIDOR) {
    if (!servidor) return { erro: "O servidor de licenças ainda não está no ar." };
    try {
      const resposta = await fetch(`${servidor}/renovar`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chave }),
      });
      const dados = await resposta.json();
      return resposta.ok && dados.chave ? { chave: dados.chave } : { erro: dados.erro || `Erro ${resposta.status}` };
    } catch {
      return { erro: "Sem conexão com o servidor de licenças." };
    }
  }

  const ambiente = typeof self !== "undefined" ? self : globalThis;
  ambiente.veuLicenca = { verificar, renovar, CHAVE_PUBLICA, SERVIDOR, PREFIXO };
})();
