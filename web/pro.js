// Véu Pro na página: a pessoa cola a chave aqui, e ela é conferida sem internet (licenca.js, a mesma da extensão).
// A chave e as listas próprias ficam no armazenamento deste navegador (localStorage) até a pessoa remover.
// A página nunca fala com o servidor de licenças: a política de segurança dela bloqueia conexões.
(() => {
  "use strict";
  const CHAVE = "veu-pro-chave";
  const LISTAS = "veu-pro-listas";
  const ouvintes = new Set();
  let estado = { ativo: false, listaNomes: [], listaTermos: [] };

  const ler = (nome, padrao) => {
    try {
      return JSON.parse(localStorage.getItem(nome) || "null") ?? padrao;
    } catch {
      return padrao;
    }
  };
  const gravar = (nome, valor) => {
    try {
      if (valor === null) localStorage.removeItem(nome);
      else localStorage.setItem(nome, JSON.stringify(valor));
    } catch { /* sem armazenamento: vale só nesta visita */ }
  };
  const limpar = (lista) => [...new Set((Array.isArray(lista) ? lista : []).map((item) => String(item).trim())
    .filter((item) => item.length >= 2 && item.length <= 200))].slice(0, 2000);

  async function conferir(chave) {
    const listas = ler(LISTAS, {});
    const base = { listaNomes: limpar(listas.nomes), listaTermos: limpar(listas.termos) };
    if (!chave || !window.veuLicenca) return { ativo: false, ...base };
    const resultado = await window.veuLicenca.verificar(chave);
    const licenca = resultado.licenca;
    return { ...base, ativo: resultado.valida, motivo: resultado.motivo, exp: licenca?.exp, email: licenca?.email,
      plano: licenca?.plano, assinatura: Boolean(licenca?.assinatura && !String(licenca.assinatura).startsWith("manual")) };
  }

  async function recarregar() {
    estado = await conferir(ler(CHAVE, ""));
    for (const ouvinte of ouvintes) ouvinte(estado);
    return estado;
  }

  window.veuPro = {
    pronto: recarregar(),
    get estado() { return estado; },
    aoMudar: (ouvinte) => ouvintes.add(ouvinte),
    /** Guarda a chave se ela for do Véu e estiver válida: { ok } ou { motivo }. */
    async ativar(chave) {
      const texto = String(chave || "").trim();
      const resultado = await conferir(texto);
      if (!resultado.ativo) return { motivo: resultado.motivo || "formato", exp: resultado.exp };
      gravar(CHAVE, texto);
      await recarregar();
      return { ok: true };
    },
    async remover() {
      gravar(CHAVE, null);
      await recarregar();
    },
    async salvarListas(nomes, termos) {
      gravar(LISTAS, { nomes: limpar(nomes), termos: limpar(termos) });
      await recarregar();
    },
    /** As listas valem só com a chave ativa. */
    termos: () => (estado.ativo ? { PESSOA: estado.listaNomes, TERMO: estado.listaTermos } : undefined),
  };
})();
