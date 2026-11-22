// Leitor de imagens do Véu Pro para os sites de IA. No Chrome e no Edge roda numa página escondida da extensão
// (leitor.html, aberta pelo fundo.js com a API offscreen); no Firefox, na própria página de fundo. Recebe a imagem
// e a configuração (tipos desligados, valores ignorados, listas próprias) e devolve a imagem com tarjas.
"use strict";
(() => {
  /** O Véu com a mesma configuração dos sites de IA (igual à página de arquivos). */
  function veuDa(config) {
    const { Veu, GROUPS } = globalThis.veu;
    const permitidos = config.tipos?.length ? config.tipos : GROUPS.flatMap((grupo) => grupo.tipos);
    const ligados = permitidos.filter((tipo) => !(config.tiposDesligados || []).includes(tipo));
    return new Veu({
      labels: ligados.length < permitidos.length || config.tipos?.length ? ligados : undefined,
      allowlist: config.ignorar || [],
      allowPatterns: config.ignorarPadroes || [],
      terms: { PESSOA: config.listaNomes || [], TERMO: config.listaTermos || [] },
    });
  }

  function dataUrlParaBlob(dados) {
    const [cabecalho, base64] = dados.split(",");
    const binario = atob(base64);
    const bytes = new Uint8Array(binario.length);
    for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
    return new Blob([bytes], { type: /^data:([^;]+)/.exec(cabecalho)[1] });
  }

  const paraDataUrl = (blob) => new Promise((pronto, erro) => {
    const leitor = new FileReader();
    leitor.onload = () => pronto(leitor.result);
    leitor.onerror = () => erro(leitor.error);
    leitor.readAsDataURL(blob);
  });

  async function ler({ dados, config }) {
    const veu = veuDa(config);
    const { blob, counts, qr } = await globalThis.veuImagens.proteger(dataUrlParaBlob(dados), (texto) => veu.analyze(texto));
    return { dados: await paraDataUrl(blob), counts, qr };
  }

  globalThis.veuLeitor = (pedido) => ler(pedido).catch((erro) => ({ erro: erro?.message || "Não consegui ler a imagem." }));

  // Na página escondida: atende só aos pedidos do fundo.js para o leitor.
  if (location.pathname.endsWith("/leitor.html")) {
    chrome.runtime.onMessage.addListener((mensagem, _remetente, responder) => {
      if (mensagem?.alvo !== "leitor") return false;
      globalThis.veuLeitor(mensagem).then(responder);
      return true;
    });
  }
})();
