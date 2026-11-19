// Teste de ponta a ponta da extensão e da página web num Chrome de verdade (sem janela).
//
//   node extensao/teste/e2e.mjs [caminho do chrome]
//
// Controla o Chrome pelo protocolo de depuração (pipe), carrega a extensão e usa uma página de chat falsa que imita
// os editores do ChatGPT e do Claude: colar e Enter são eventos de verdade (isTrusted), como os de uma pessoa.
import { spawn } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHROMES = [
  process.argv[2], process.env.CHROME,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const chrome = CHROMES.find((caminho) => existsSync(caminho));
if (!chrome) {
  console.error("Chrome não encontrado. Passe o caminho: node extensao/teste/e2e.mjs /caminho/do/chrome");
  process.exit(1);
}

const CPF = "529.982.247-25";
let falhas = 0;
function confere(condicao, descricao) {
  console.log(`${condicao ? "ok  " : "FALHOU"} ${descricao}`);
  if (!condicao) falhas += 1;
}

// Servidor local: a página web e um chat falso.
const CHAT = `<!doctype html><meta charset="utf-8"><title>Chat falso</title>
<div id="conversa"></div>
<div id="prompt-textarea" contenteditable="true" style="min-height:40px;border:1px solid #999"></div>
<button aria-label="Enviar mensagem" id="enviar">Enviar</button>
<script>
  window.enviadas = [];
  const campo = document.getElementById("prompt-textarea");
  // Como o ProseMirror: o próprio editor trata o colar.
  campo.addEventListener("paste", (e) => {
    e.preventDefault();
    document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
  });
  function enviar() {
    const texto = campo.innerText.trim();
    if (!texto) return;
    window.enviadas.push(texto);
    campo.textContent = "";
    setTimeout(() => {
      const resposta = document.createElement("p");
      resposta.className = "resposta";
      resposta.textContent = "Recebi: " + texto;
      document.getElementById("conversa").append(resposta);
    }, 30);
  }
  campo.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } });
  document.getElementById("enviar").addEventListener("click", enviar);
</script>`;
const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png" };
const servidor = createServer((pedido, resposta) => {
  const caminho = new URL(pedido.url, "http://x").pathname;
  if (caminho === "/chat") {
    resposta.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return resposta.end(CHAT);
  }
  if (caminho.startsWith("/web/")) {
    const arquivo = join(raiz, "web", caminho.slice(5) || "index.html");
    if (existsSync(arquivo)) {
      resposta.writeHead(200, { "content-type": TIPOS[extname(arquivo)] || "application/octet-stream" });
      return resposta.end(readFileSync(arquivo));
    }
  }
  resposta.writeHead(404).end();
});
await new Promise((pronto) => servidor.listen(0, "127.0.0.1", pronto));
const base = `http://127.0.0.1:${servidor.address().port}`;

// Cópia da extensão que também roda no chat falso.
const temporaria = mkdtempSync(join(tmpdir(), "veu-e2e-"));
const extensao = join(temporaria, "extensao");
cpSync(join(raiz, "extensao"), extensao, { recursive: true, filter: (origem) => !origem.includes(`${join("extensao", "teste")}`) });
const manifesto = JSON.parse(readFileSync(join(extensao, "manifest.json"), "utf8"));
manifesto.content_scripts[0].matches.push("http://127.0.0.1/*");
writeFileSync(join(extensao, "manifest.json"), JSON.stringify(manifesto));

// Chrome com pipe de depuração (fd 3 escreve para o Chrome, fd 4 lê dele).
const processo = spawn(chrome, [
  "--headless=new", "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--no-first-run",
  "--no-default-browser-check", `--user-data-dir=${join(temporaria, "perfil")}`,
  // Nos executores Linux do CI, o sandbox do Chrome pode não ter permissão de criar namespaces.
  ...(process.platform === "linux" ? ["--no-sandbox"] : []), "about:blank",
], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
const [, , , entrada, saida] = processo.stdio;
let proximo = 0;
const esperando = new Map();
let buffer = "";
saida.on("data", (pedaco) => {
  buffer += pedaco.toString("utf8");
  let fim;
  while ((fim = buffer.indexOf("\0")) !== -1) {
    const mensagem = JSON.parse(buffer.slice(0, fim));
    buffer = buffer.slice(fim + 1);
    const pendente = esperando.get(mensagem.id);
    if (pendente) {
      esperando.delete(mensagem.id);
      if (mensagem.error) pendente.rejeitar(new Error(`${mensagem.error.message}`));
      else pendente.resolver(mensagem.result);
    }
  }
});
function cdp(method, params = {}, sessionId) {
  const id = ++proximo;
  entrada.write(`${JSON.stringify({ id, method, params, sessionId })}\0`);
  return new Promise((resolver, rejeitar) => esperando.set(id, { resolver, rejeitar }));
}
const pausa = (ms) => new Promise((pronto) => setTimeout(pronto, ms));

// PDF mínimo com uma linha de texto (fonte Helvetica), para a página de arquivos ler com o pdf.js.
function pdfCom(texto) {
  const conteudo = `BT /F1 12 Tf 72 720 Td (${texto}) Tj ET`;
  const objetos = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${conteudo.length} >>\nstream\n${conteudo}\nendstream`, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];
  let pdf = "%PDF-1.4\n";
  const posicoes = objetos.map((objeto, i) => {
    const posicao = pdf.length;
    pdf += `${i + 1} 0 obj\n${objeto}\nendobj\n`;
    return posicao;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n${posicoes.map((p) => `${String(p).padStart(10, "0")} 00000 n \n`).join("")}`;
  return `${pdf}trailer\n<< /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
}

async function enviarArquivo(pagina, seletor, caminho) {
  const { result } = await cdp("Runtime.evaluate", { expression: `document.querySelector(${JSON.stringify(seletor)})` }, pagina.sessionId);
  await cdp("DOM.setFileInputFiles", { files: [caminho], objectId: result.objectId }, pagina.sessionId);
}

async function esperarArquivo(caminho) {
  for (let i = 0; i < 40 && !existsSync(caminho); i++) await pausa(250);
  return existsSync(caminho);
}

async function testarPro(id) {
  const { writeZip, readZip } = await import("../../js/dist/index.js").then((m) => m.default ?? m);
  const downloads = join(temporaria, "baixados");
  await cdp("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });

  const icone = await abrir(`chrome-extension://${id}/popup.html`);
  // O teste anterior desmarcou "Documentos": volta a esconder CPF.
  if (!(await icone.avaliar(`document.getElementById("grupo-documentos").checked`))) {
    await icone.avaliar(`document.getElementById("grupo-documentos").click()`);
    await pausa(400);
  }
  await icone.avaliar(`document.getElementById("pro-chave").value = ${JSON.stringify(process.env.VEU_E2E_LICENCA)}`);
  await icone.avaliar(`document.getElementById("pro-botao").click()`);
  await pausa(800);
  const estado = await icone.avaliar(`document.getElementById("pro-estado").textContent`);
  confere(/ativo até/.test(estado), `a chave do Pro ativa pelo ícone (${estado})`);
  await icone.avaliar(`document.getElementById("lista-nomes").value = "Joana Prado"; document.getElementById("salvar-listas").click()`);
  await pausa(500);
  await icone.fechar();

  const chat = await abrir(`${base}/chat`);
  await chat.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await chat.digitar("Encaminhe para a JOANA PRADO, CPF 529.982.247-25");
  await chat.enter();
  await pausa(300);
  const comLista = await chat.avaliar(`document.getElementById("prompt-textarea").innerText`);
  confere(!/joana/i.test(comLista) && comLista.includes("[PESSOA_1]") && comLista.includes("[CPF_1]"),
    `a lista própria esconde o nome em maiúsculas (${comLista.trim()})`);
  await chat.fechar();

  const relatorio = await abrir(`chrome-extension://${id}/relatorio.html`);
  const total = await relatorio.avaliar(`document.getElementById("total").textContent`);
  confere(Number(total) > 0, `o relatório do mês conta os dados escondidos (${total})`);
  await relatorio.fechar();

  const arquivos = await abrir(`chrome-extension://${id}/arquivos.html`);
  const docx = join(temporaria, "contrato.docx");
  const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
  writeFileSync(docx, await writeZip(new Map([["word/document.xml", new TextEncoder().encode(
    `<w:document ${W}><w:body><w:p><w:r><w:t>Contratante Maria Souza, CPF ${CPF}</w:t></w:r></w:p></w:body></w:document>`)]])));
  await enviarArquivo(arquivos, "#proteger", docx);
  const saidaDocx = join(downloads, "contrato-protegido.docx");
  const baixouDocx = await esperarArquivo(saidaDocx);
  const xml = baixouDocx ? new TextDecoder().decode((await readZip(new Uint8Array(readFileSync(saidaDocx)))).get("word/document.xml")) : "";
  confere(xml.includes("[PESSOA_1]") && !xml.includes("Souza") && !xml.includes("529.982"), `o Word protegido é baixado sem os dados (${xml.slice(-80)})`);

  const pdf = join(temporaria, "laudo.pdf");
  writeFileSync(pdf, pdfCom(`Paciente Maria Souza, CPF ${CPF}`));
  await enviarArquivo(arquivos, "#proteger", pdf);
  const saidaPdf = join(downloads, "laudo-protegido.txt");
  const textoPdf = (await esperarArquivo(saidaPdf)) ? readFileSync(saidaPdf, "utf8") : "";
  confere(textoPdf.includes("[PESSOA_1]") && textoPdf.includes("[CPF_1]") && !textoPdf.includes("Souza"),
    `o PDF vira texto protegido pelo pdf.js (${textoPdf.replace(/\n/g, " ").slice(0, 80)})`);

  await arquivos.fechar();
}

async function abrir(url) {
  const { targetId } = await cdp("Target.createTarget", { url });
  const { sessionId } = await cdp("Target.attachToTarget", { targetId, flatten: true });
  await cdp("Runtime.enable", {}, sessionId);
  await pausa(1200);
  return {
    sessionId,
    avaliar: async (expressao) => {
      const { result, exceptionDetails } = await cdp("Runtime.evaluate", { expression: expressao, awaitPromise: true, returnByValue: true }, sessionId);
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
      return result.value;
    },
    digitar: (texto) => cdp("Input.insertText", { text: texto }, sessionId),
    enter: async () => {
      for (const type of ["keyDown", "keyUp"]) {
        await cdp("Input.dispatchKeyEvent", { type, key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: type === "keyDown" ? "\r" : undefined }, sessionId);
      }
    },
    fechar: () => cdp("Target.closeTarget", { targetId }),
  };
}

try {
  // Página web: tudo no navegador.
  const web = await abrir(`${base}/web/index.html`);
  await web.avaliar(`document.getElementById("entrada").focus()`);
  await web.digitar(`A cliente Maria Souza, CPF ${CPF}, ligou.`);
  await pausa(400);
  const protegido = await web.avaliar(`document.getElementById("saida").textContent`);
  confere(protegido === "A cliente [PESSOA_1], CPF [CPF_1], ligou.", `página web protege o texto (${protegido})`);
  await web.avaliar(`document.getElementById("copiar-protegido").click()`);
  await web.avaliar(`document.getElementById("resposta").focus()`);
  await web.digitar("Olá [PESSOA_1], seu CPF é [CPF_1].");
  await pausa(200);
  const restaurado = await web.avaliar(`document.getElementById("restaurado").textContent`);
  confere(restaurado === `Olá Maria Souza, seu CPF é ${CPF}.`, "página web restaura a resposta");
  // Texto grande: analisado no trabalhador (Web Worker), sem travar a página.
  await web.avaliar(`(() => { const e = document.getElementById("entrada"); e.value = "Relatório do atendimento. ".repeat(1200) + "Cliente Maria Souza, CPF ${CPF}."; e.dispatchEvent(new Event("input")); })()`);
  let grande = "";
  for (let tentativa = 0; tentativa < 40 && !grande.includes("[CPF_1]"); tentativa += 1) {
    await pausa(150);
    grande = await web.avaliar(`document.getElementById("saida").textContent`);
  }
  confere(grande.includes("[CPF_1]") && !grande.includes(CPF), "texto grande protegido pelo trabalhador da página");
  if (process.env.VEU_CAPTURA) {
    await cdp("Emulation.setDeviceMetricsOverride", { width: 900, height: 1250, deviceScaleFactor: 1, mobile: false }, web.sessionId);
    const { data } = await cdp("Page.captureScreenshot", { format: "png" }, web.sessionId);
    writeFileSync(join(process.env.VEU_CAPTURA, "web.png"), Buffer.from(data, "base64"));
  }
  await web.fechar();

  // Idiomas: ?lang= escolhe o português ou o inglês (sem ele, vale o idioma do navegador).
  for (const [idioma, titulo, html] of [["en", "Your text", "en"], ["pt", "Seu texto", "pt-BR"]]) {
    const pagina = await abrir(`${base}/web/index.html?lang=${idioma}`);
    const visto = await pagina.avaliar(`[document.querySelector('[data-t="seuTexto"]').textContent, document.documentElement.lang]`);
    confere(visto[0] === titulo && visto[1] === html, `página em ${idioma} (${visto.join(", ")})`);
    await pagina.fechar();
  }

  // Caixinhas de "O que esconder": desmarcar um grupo deixa aquele tipo passar, e a escolha fica salva.
  const caixas = await abrir(`${base}/web/index.html?lang=pt`);
  const grupos = await caixas.avaliar(`document.querySelectorAll("#tipos-grupos .grupo").length`);
  confere(grupos === 7, `a página mostra os 7 grupos (${grupos})`);
  await caixas.avaliar(`document.getElementById("entrada").focus()`);
  await caixas.digitar("Servidor 10.0.0.5:8080 da Maria Souza");
  await pausa(400);
  let comCaixas = await caixas.avaliar(`document.getElementById("saida").textContent`);
  confere(comCaixas === "Servidor [IP_1]:[PORTA_1] da [PESSOA_1]", `IP e porta escondidos (${comCaixas})`);
  await caixas.avaliar(`document.getElementById("grupo-infra").click()`);
  await pausa(300);
  comCaixas = await caixas.avaliar(`document.getElementById("saida").textContent`);
  confere(comCaixas === "Servidor 10.0.0.5:8080 da [PESSOA_1]", `sem o grupo, IP e porta passam (${comCaixas})`);
  await caixas.fechar();
  const recarregada = await abrir(`${base}/web/index.html?lang=pt`);
  const lembrou = await recarregada.avaliar(`[document.getElementById("grupo-infra").checked, document.getElementById("grupo-pessoas").checked]`);
  confere(lembrou[0] === false && lembrou[1] === true, "a escolha fica salva no navegador");
  await recarregada.avaliar(`document.getElementById("grupo-infra").click()`);
  await recarregada.fechar();

  // Extensão
  const { id } = await cdp("Extensions.loadUnpacked", { path: extensao });
  confere(Boolean(id), "extensão carregada");
  const popup = await abrir(`chrome-extension://${id}/popup.html`);
  // A restauração na página vem desligada por padrão (o site também leria os dados); o teste liga.
  await popup.avaliar(`chrome.storage.sync.set({ modo: "proteger", restaurarRespostas: true,
    orientacao: "Dados de clientes só no assistente interno.", linkOrientacao: "https://intranet.example/ia" })`);
  await popup.fechar();

  const chat = await abrir(`${base}/chat`);
  await chat.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await chat.digitar(`Resuma o caso da cliente Maria Souza, CPF ${CPF}`);
  await chat.enter();
  await pausa(300);
  let enviadas = await chat.avaliar("window.enviadas");
  let campo = await chat.avaliar(`document.getElementById("prompt-textarea").innerText`);
  confere(enviadas.length === 0, "modo proteger segura o primeiro Enter");
  confere(campo.includes("[CPF_1]") && !campo.includes(CPF), `o campo passa a ter marcadores (${campo.trim()})`);
  // O aviso fica num shadow DOM fechado: o CDP atravessa (pierce) para conferir a orientação da empresa.
  const arvore = JSON.stringify(await cdp("DOM.getDocument", { depth: -1, pierce: true }, chat.sessionId));
  confere(arvore.includes("Dados de clientes só no assistente interno.") && arvore.includes("https://intranet.example/ia"),
    "o aviso mostra a orientação e o link da empresa");
  await chat.enter();
  await pausa(300);
  enviadas = await chat.avaliar("window.enviadas");
  confere(enviadas.length === 1 && !enviadas[0].includes(CPF) && enviadas[0].includes("[PESSOA_1]"), `o site recebe só marcadores (${enviadas[0]})`);
  await pausa(300);
  const respostaNaTela = await chat.avaliar(`document.querySelector(".resposta")?.textContent`);
  confere(respostaNaTela?.includes(CPF) && respostaNaTela.includes("Maria Souza"), `a resposta mostra os dados reais na tela (${respostaNaTela})`);

  // Colar: entra protegido (pelo próprio tratamento de colar do editor).
  await cdp("Browser.grantPermissions", { permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"], origin: base });
  await chat.avaliar(`navigator.clipboard.writeText("Telefone da Ana Lima: (11) 98765-4321")`);
  await chat.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "v", code: "KeyV", modifiers: process.platform === "darwin" ? 4 : 2, commands: ["paste"] }, chat.sessionId);
  await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "v", code: "KeyV" }, chat.sessionId);
  await pausa(300);
  campo = await chat.avaliar(`document.getElementById("prompt-textarea").innerText`);
  confere(campo.includes("[TELEFONE_1]") && !campo.includes("98765-4321"), `colar entra protegido (${campo.trim()})`);
  await chat.fechar();

  // Caixinhas do ícone da extensão: com "Documentos" desmarcado, o CPF passa e o nome continua escondido.
  const icone = await abrir(`chrome-extension://${id}/popup.html`);
  const gruposNoIcone = await icone.avaliar(`document.querySelectorAll("#grupos label").length`);
  confere(gruposNoIcone === 7, `o ícone mostra os 7 grupos (${gruposNoIcone})`);
  await icone.avaliar(`document.getElementById("grupo-documentos").click()`);
  await pausa(400);
  await icone.fechar();
  const chat2 = await abrir(`${base}/chat`);
  await chat2.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await chat2.digitar(`A cliente Maria Souza, CPF ${CPF}`);
  await chat2.enter();
  await pausa(300);
  const semDocumentos = await chat2.avaliar(`document.getElementById("prompt-textarea").innerText`);
  confere(semDocumentos.includes("[PESSOA_1]") && semDocumentos.includes(CPF), `sem o grupo, o CPF passa (${semDocumentos.trim()})`);
  await chat2.fechar();

  // Véu Pro: só com uma chave de teste (VEU_E2E_LICENCA), emitida por nuvem/emitir-licenca.mjs com poucos dias.
  if (process.env.VEU_E2E_LICENCA) await testarPro(id);
} catch (erro) {
  falhas += 1;
  console.error(erro);
} finally {
  processo.kill();
  servidor.close();
  await pausa(500);
  try {
    rmSync(temporaria, { recursive: true, force: true });
  } catch { /* o Chrome ainda pode estar soltando o perfil */ }
}
console.log(falhas ? `\n${falhas} falha(s)` : "\nTudo certo.");
process.exit(falhas ? 1 : 0);
