// Grava a demonstração da página web (docs/demo.gif) num Chrome sem janela.
//
//   node scripts/gravar_demo.mjs [--idioma en]     # quadros em build/demo-pt/ ou demo-en/ (precisa de web/veu.global.js)
//   python scripts/montar_gif.py [--idioma en]     # junta os quadros em docs/demo.gif ou docs/demo-en.gif
//
// Os dados são fictícios: o CPF é o de exemplo dos testes e o e-mail usa example.com.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const idioma = process.argv.includes("en") ? "en" : "pt";
const chrome = [process.env.CHROME, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
  .filter(Boolean).find((caminho) => existsSync(caminho));
if (!chrome) throw new Error("Chrome não encontrado");
if (!existsSync(join(raiz, "web", "veu.global.js"))) throw new Error("Falta web/veu.global.js: rode scripts/empacotar_navegador.py");

const TEXTOS = {
  pt: ["Resuma: a cliente Maria Souza (maria.souza@example.com), CPF 529.982.247-25, ligou do (11) 98765-4321 pedindo o estorno.",
    "Resumo: [PESSOA_1] ([EMAIL_1]) pediu o estorno. Retornar no [TELEFONE_1]."],
  en: ["Summarize: customer Maria Souza (maria.souza@example.com), SSN 123-45-6789, called from +1 415 555 2671 asking for a refund.",
    "Summary: [PESSOA_1] ([EMAIL_1]) asked for a refund. Call back at [TELEFONE_1]."],
};
const [PERGUNTA, RESPOSTA] = TEXTOS[idioma];
const saidaQuadros = join(raiz, "build", `demo-${idioma}`);
rmSync(saidaQuadros, { recursive: true, force: true });
mkdirSync(saidaQuadros, { recursive: true });

const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css" };
const servidor = createServer((pedido, resposta) => {
  const arquivo = join(raiz, "web", new URL(pedido.url, "http://x").pathname.slice(1) || "index.html");
  if (!existsSync(arquivo)) return resposta.writeHead(404).end();
  resposta.writeHead(200, { "content-type": TIPOS[extname(arquivo)] || "application/octet-stream" });
  resposta.end(readFileSync(arquivo));
});
await new Promise((pronto) => servidor.listen(0, "127.0.0.1", pronto));

const temporaria = mkdtempSync(join(tmpdir(), "veu-demo-"));
const processo = spawn(chrome, ["--headless=new", "--remote-debugging-pipe", "--no-first-run", "--hide-scrollbars",
  `--user-data-dir=${join(temporaria, "perfil")}`, ...(process.platform === "linux" ? ["--no-sandbox"] : []), "about:blank"],
{ stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
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
      if (mensagem.error) pendente.rejeitar(new Error(mensagem.error.message));
      else pendente.resolver(mensagem.result);
    }
  }
});
const cdp = (method, params = {}, sessionId) => {
  const id = ++proximo;
  entrada.write(`${JSON.stringify({ id, method, params, sessionId })}\0`);
  return new Promise((resolver, rejeitar) => esperando.set(id, { resolver, rejeitar }));
};
const pausa = (ms) => new Promise((pronto) => setTimeout(pronto, ms));

const quadros = [];
try {
  const { targetId } = await cdp("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp("Target.attachToTarget", { targetId, flatten: true });
  const s = sessionId;
  await cdp("Emulation.setDeviceMetricsOverride", { width: 760, height: 1400, deviceScaleFactor: 1, mobile: false }, s);
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] }, s);
  await cdp("Page.navigate", { url: `http://127.0.0.1:${servidor.address().port}/index.html?lang=${idioma}` }, s);
  await pausa(1500);
  const avaliar = async (expressao) => (await cdp("Runtime.evaluate", { expression: expressao, returnByValue: true }, s)).result.value;
  // Recorte: dos três passos (texto, texto protegido, resposta), medido com tudo preenchido; depois, apaga tudo.
  await avaliar(`(() => {
    const preencher = (id, texto) => { const e = document.getElementById(id); e.value = texto; e.dispatchEvent(new Event("input")); };
    preencher("entrada", ${JSON.stringify(PERGUNTA)});
    document.getElementById("copiar-protegido").click();
    preencher("resposta", ${JSON.stringify(RESPOSTA)});
  })()`);
  await pausa(500);
  const recorte = await avaliar(`(() => {
    const paineis = [...document.querySelectorAll(".painel")].slice(0, 3);
    const a = paineis[0].getBoundingClientRect(), b = paineis[2].getBoundingClientRect();
    return { x: a.left - 12, y: a.top - 12, width: a.width + 24, height: b.bottom - a.top + 24, scale: 1 };
  })()`);
  await avaliar(`document.getElementById("limpar").click()`);
  await pausa(300);
  const capturar = async (duracao) => {
    const { data } = await cdp("Page.captureScreenshot", { format: "png", clip: recorte }, s);
    const nome = `${String(quadros.length).padStart(3, "0")}.png`;
    writeFileSync(join(saidaQuadros, nome), Buffer.from(data, "base64"));
    quadros.push({ arquivo: nome, ms: duracao });
  };
  const digitar = async (campo, texto, passo) => {
    await avaliar(`document.getElementById("${campo}").focus()`);
    for (let i = 0; i < texto.length; i += passo) {
      await cdp("Input.insertText", { text: texto.slice(i, i + passo) }, s);
      await pausa(60);
      await capturar(90);
    }
  };
  await cdp("Browser.grantPermissions", { permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"],
    origin: `http://127.0.0.1:${servidor.address().port}` });
  await capturar(900);
  await digitar("entrada", PERGUNTA, 6);
  await pausa(300);
  await capturar(1800);
  await avaliar(`document.getElementById("copiar-protegido").click()`);  // a pessoa copia o texto para a IA
  await pausa(300);
  await capturar(1400);
  await digitar("resposta", RESPOSTA, 6);
  await pausa(300);
  await capturar(3800);
  writeFileSync(join(saidaQuadros, "quadros.json"), JSON.stringify(quadros, null, 1));
  const protegido = await avaliar(`document.getElementById("saida").textContent`);
  const restaurado = await avaliar(`document.getElementById("restaurado").textContent`);
  console.log(`${quadros.length} quadros em build/demo-${idioma}\nprotegido: ${protegido}\nrestaurado: ${restaurado}`);
} finally {
  processo.kill();
  servidor.close();
  await pausa(300);
  try { rmSync(temporaria, { recursive: true, force: true }); } catch { /* o Chrome ainda pode estar soltando o perfil */ }
}
