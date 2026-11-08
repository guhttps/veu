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
