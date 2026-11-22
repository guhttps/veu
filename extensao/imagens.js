// Imagens (Véu Pro): lê o print com o Tesseract, que roda inteiro no navegador (nada sai daqui), acha os dados com o
// Véu e pinta tarjas pretas por cima. QR Codes também são cobertos (podem carregar um Pix com nome e chave). Os
// arquivos do leitor ficam na pasta ocr/ ao lado da página e só são carregados quando aparece a primeira imagem.
// O mesmo arquivo serve à extensão (páginas do Véu Pro) e ao site (scripts/empacotar_navegador.py copia).
(() => {
  "use strict";
  const PASTA = "ocr/";
  const TIPOS = new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp"]);
  let leitor = null; // o worker do Tesseract, reaproveitado entre imagens

  function carregar(arquivo) {
    return new Promise((pronto, erro) => {
      const script = document.createElement("script");
      script.src = new URL(PASTA + arquivo, document.baseURI).href;
      script.onload = pronto;
      script.onerror = () => erro(new Error("Não deu para carregar o leitor de imagens."));
      document.head.append(script);
    });
  }

  function obterLeitor() {
    leitor ??= (async () => {
      if (!globalThis.Tesseract) await carregar("tesseract.min.js");
      const base = new URL(PASTA, document.baseURI).href;
      // Português no modo LSTM (o mais leve e preciso para prints); sem cache em IndexedDB e sem worker em blob:,
      // para valer a política de segurança da página.
      return globalThis.Tesseract.createWorker("por", 1, {
        workerPath: base + "worker.min.js", corePath: base + "tesseract-core-simd-lstm.wasm.js", langPath: base,
        gzip: true, workerBlobURL: false, cacheMethod: "none",
      });
    })().catch((erro) => {
      leitor = null;
      throw erro;
    });
    return leitor;
  }

  /** Caixas dos QR Codes da imagem: acha um, cobre e procura de novo (até 8). */
  async function caixasDeQr(contexto, largura, altura) {
    if (!globalThis.jsQR) await carregar("jsQR.js");
    const imagem = contexto.getImageData(0, 0, largura, altura);
    const caixas = [];
    for (let vez = 0; vez < 8; vez++) {
      const achado = globalThis.jsQR(imagem.data, largura, altura, { inversionAttempts: "attemptBoth" });
      if (!achado) break;
      const cantos = [achado.location.topLeftCorner, achado.location.topRightCorner, achado.location.bottomLeftCorner,
        achado.location.bottomRightCorner];
      const xs = cantos.map((c) => c.x);
      const ys = cantos.map((c) => c.y);
      // Margem de um módulo e meio em volta: sem ela, sobram os quadrados de posição do código.
      const margem = Math.max(8, (Math.max(...xs) - Math.min(...xs)) / 12);
      const caixa = { x0: Math.min(...xs) - margem, y0: Math.min(...ys) - margem, x1: Math.max(...xs) + margem, y1: Math.max(...ys) + margem };
      caixas.push(caixa);
      // Pinta de branco na cópia de trabalho para achar o próximo.
      for (let y = Math.max(0, Math.floor(caixa.y0)); y < Math.min(altura, Math.ceil(caixa.y1)); y++) {
        for (let x = Math.max(0, Math.floor(caixa.x0)); x < Math.min(largura, Math.ceil(caixa.x1)); x++) {
          imagem.data.fill(255, (y * largura + x) * 4, (y * largura + x) * 4 + 3);
        }
      }
    }
    return caixas;
  }

  /**
   * Protege uma imagem: devolve { blob (PNG com as tarjas), counts (dados por tipo), qr (quantos QR Codes) }.
   * `analisar` é o Véu já configurado: (texto) => veu.analyze(texto).
   */
  async function proteger(arquivo, analisar) {
    const { imageRedactions, wordsFromTesseract } = globalThis.veu;
    const bitmap = await createImageBitmap(arquivo);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const contexto = canvas.getContext("2d", { willReadFrequently: true });
    contexto.drawImage(bitmap, 0, 0);
    bitmap.close();
    const worker = await obterLeitor();
    const { data } = await worker.recognize(canvas, {}, { blocks: true });
    const { boxes, counts } = imageRedactions(wordsFromTesseract(data.blocks), analisar);
    const qr = await caixasDeQr(contexto, canvas.width, canvas.height);
    contexto.fillStyle = "#000";
    for (const caixa of [...boxes, ...qr]) contexto.fillRect(caixa.x0, caixa.y0, caixa.x1 - caixa.x0, caixa.y1 - caixa.y0);
    const blob = await new Promise((pronto) => canvas.toBlob(pronto, "image/png"));
    return { blob, counts, qr: qr.length };
  }

  const ehImagem = (nome) => TIPOS.has(String(nome).toLowerCase().split(".").pop());
  globalThis.veuImagens = { proteger, ehImagem };
})();
