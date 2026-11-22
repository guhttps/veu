// Imagens (Véu Pro): lê o print com o Tesseract, que roda inteiro no navegador (nada sai daqui), acha os dados com o
// Véu e pinta tarjas pretas por cima. Também cobre QR Codes (podem carregar um Pix com nome e chave), códigos de
// barras, assinaturas e rostos. Os arquivos ficam na pasta ocr/ ao lado da página e só são carregados quando
// aparece a primeira imagem. O mesmo arquivo serve à extensão e ao site (scripts/empacotar_navegador.py copia).
(() => {
  "use strict";
  const PASTA = "ocr/";
  const TIPOS = new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp"]);
  const PIXELS_PARA_REDUZIR = 6_000_000; // códigos de barras e assinaturas são procurados numa cópia menor
  let leitor = null; // o worker do Tesseract, reaproveitado entre imagens
  let rostos = null; // o detector de rostos (face-api), carregado na primeira imagem

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

  // Rostos: o detector pequeno do face-api (TinyFaceDetector). O modelo vem num script (rostos-modelo.js), não por
  // fetch: a página do site bloqueia conexões, e assim continua bloqueando.
  function obterRostos() {
    rostos ??= (async () => {
      if (!globalThis.faceapi) await carregar("face-api.js");
      if (!globalThis.veuModeloRostos) await carregar("rostos-modelo.js");
      const { faceapi, veuModeloRostos: modelo } = globalThis;
      const binario = atob(modelo.pesos);
      const bytes = new Uint8Array(binario.length);
      for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
      const pesos = faceapi.tf.io.decodeWeights(bytes.buffer, modelo.manifesto.flatMap((grupo) => grupo.weights));
      await faceapi.nets.tinyFaceDetector.loadFromWeightMap(pesos);
      return faceapi;
    })().catch((erro) => {
      rostos = null;
      throw erro;
    });
    return rostos;
  }

  async function caixasDeRostos(canvas) {
    const faceapi = await obterRostos();
    const achados = await faceapi.detectAllFaces(canvas, new faceapi.TinyFaceDetectorOptions({ inputSize: 512, scoreThreshold: 0.4 }));
    // A caixa do detector pega olhos, nariz e boca: a tarja cobre também testa, cabelo, orelhas e queixo.
    return achados.map(({ box }) => ({ x0: box.x - box.width * 0.2, y0: box.y - box.height * 0.35,
      x1: box.x + box.width * 1.2, y1: box.y + box.height * 1.25 }));
  }

  /** Caixas dos QR Codes (numa cópia dos pixels): acha um, apaga na cópia e procura de novo (até 8). */
  async function caixasDeQr(original) {
    if (!globalThis.jsQR) await carregar("jsQR.js");
    const { width: largura, height: altura } = original;
    const dados = new Uint8ClampedArray(original.data);
    const caixas = [];
    for (let vez = 0; vez < 8; vez++) {
      const achado = globalThis.jsQR(dados, largura, altura, { inversionAttempts: "attemptBoth" });
      if (!achado) break;
      const cantos = [achado.location.topLeftCorner, achado.location.topRightCorner, achado.location.bottomLeftCorner,
        achado.location.bottomRightCorner];
      const xs = cantos.map((c) => c.x);
      const ys = cantos.map((c) => c.y);
      // Margem de um módulo e meio em volta: sem ela, sobram os quadrados de posição do código.
      const margem = Math.max(8, (Math.max(...xs) - Math.min(...xs)) / 12);
      const caixa = { x0: Math.min(...xs) - margem, y0: Math.min(...ys) - margem, x1: Math.max(...xs) + margem, y1: Math.max(...ys) + margem };
      caixas.push(caixa);
      for (let y = Math.max(0, Math.floor(caixa.y0)); y < Math.min(altura, Math.ceil(caixa.y1)); y++) {
        for (let x = Math.max(0, Math.floor(caixa.x0)); x < Math.min(largura, Math.ceil(caixa.x1)); x++) {
          dados.fill(255, (y * largura + x) * 4, (y * largura + x) * 4 + 3);
        }
      }
    }
    return caixas;
  }

  /**
   * Códigos de barras e assinaturas são procurados nos pixels (numa cópia menor se a imagem for enorme); as palavras
   * lidas com confiança ajudam a não confundir texto com barras ou rabisco.
   */
  function procurarNosPixels(canvas, palavras, procurar) {
    const escala = Math.min(1, Math.sqrt(PIXELS_PARA_REDUZIR / (canvas.width * canvas.height)));
    let alvo = canvas;
    if (escala < 1) {
      alvo = document.createElement("canvas");
      alvo.width = Math.round(canvas.width * escala);
      alvo.height = Math.round(canvas.height * escala);
      alvo.getContext("2d").drawImage(canvas, 0, 0, alvo.width, alvo.height);
    }
    const pixels = alvo.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, alvo.width, alvo.height);
    const reduzir = (b) => ({ x0: b.x0 * escala, y0: b.y0 * escala, x1: b.x1 * escala, y1: b.y1 * escala });
    const palavrasNaEscala = palavras.map((p) => ({ ...p, bbox: reduzir(p.bbox) }));
    return procurar(pixels, palavrasNaEscala)
      .map((b) => ({ x0: b.x0 / escala, y0: b.y0 / escala, x1: b.x1 / escala, y1: b.y1 / escala }));
  }

  /**
   * Protege uma imagem: devolve { blob (PNG com as tarjas), counts (o que foi coberto, por tipo) }.
   * `analisar` é o Véu já configurado: (texto) => veu.analyze(texto). `ligado(tipo)` diz se a pessoa quer esconder
   * aquele tipo (as caixinhas de "O que esconder"): QR_CODE, CODIGO_BARRAS, ASSINATURA e ROSTO.
   */
  async function proteger(arquivo, analisar, ligado = () => true) {
    const { imageRedactions, wordsFromTesseract, barcodeBoxes, signatureBoxes } = globalThis.veu;
    const bitmap = await createImageBitmap(arquivo);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const contexto = canvas.getContext("2d", { willReadFrequently: true });
    contexto.drawImage(bitmap, 0, 0);
    bitmap.close();
    const worker = await obterLeitor();
    const { data } = await worker.recognize(canvas, {}, { blocks: true });
    const palavras = wordsFromTesseract(data.blocks);
    const { boxes, counts } = imageRedactions(palavras, analisar);
    const caixas = [...boxes];
    const somar = (tipo, achadas) => {
      if (!achadas.length) return;
      counts[tipo] = (counts[tipo] || 0) + achadas.length;
      caixas.push(...achadas);
    };
    if (ligado("QR_CODE")) somar("QR_CODE", await caixasDeQr(contexto.getImageData(0, 0, canvas.width, canvas.height)));
    if (ligado("CODIGO_BARRAS")) {
      somar("CODIGO_BARRAS", procurarNosPixels(canvas, palavras, (pixels, lidas) => barcodeBoxes(pixels,
        lidas.filter((p) => (p.confidence ?? 100) >= 60 && /[\p{L}\p{N}]/u.test(p.text)).map((p) => p.bbox))));
    }
    if (ligado("ASSINATURA")) somar("ASSINATURA", procurarNosPixels(canvas, palavras, signatureBoxes));
    if (ligado("ROSTO")) somar("ROSTO", await caixasDeRostos(canvas));
    contexto.fillStyle = "#000";
    for (const caixa of caixas) contexto.fillRect(caixa.x0, caixa.y0, caixa.x1 - caixa.x0, caixa.y1 - caixa.y0);
    const blob = await new Promise((pronto) => canvas.toBlob(pronto, "image/png"));
    return { blob, counts };
  }

  const ehImagem = (nome) => TIPOS.has(String(nome).toLowerCase().split(".").pop());
  globalThis.veuImagens = { proteger, ehImagem };
})();
