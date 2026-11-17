// Capturas de tela para as lojas de extensões (Edge e Firefox), em extensao/loja/capturas/, 1280x800.
//
//   python scripts/empacotar_navegador.py && node scripts/capturas_loja.mjs
//
// Usa a extensão de verdade num Chrome sem janela e uma página de chat neutra (nenhuma marca real), com dados
// fictícios: o CPF é o de exemplo dos testes e o e-mail usa example.com.
import { spawn } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const chrome = [process.env.CHROME, "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome",
  "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].filter(Boolean).find((c) => existsSync(c));
if (!chrome) throw new Error("Chrome não encontrado");
if (!existsSync(join(raiz, "extensao", "veu.global.js"))) throw new Error("Rode antes: python scripts/empacotar_navegador.py");
const destino = join(raiz, "extensao", "loja", "capturas");
mkdirSync(destino, { recursive: true });

const ESTILO = `
  * { box-sizing: border-box; } body { margin: 0; font: 15px/1.5 system-ui, "Segoe UI", sans-serif; background: #f4f6f5; color: #1c2321; }
  header { height: 56px; display: flex; align-items: center; padding: 0 28px; background: #fff; border-bottom: 1px solid #dde3e0; font-weight: 600; }
  header small { color: #6b7672; font-weight: 400; margin-left: 10px; }
  main { max-width: 820px; margin: 0 auto; padding: 32px 24px 160px; display: grid; gap: 16px; }
  .ia { background: #fff; border: 1px solid #dde3e0; border-radius: 14px; padding: 14px 16px; }
  .eu { justify-self: end; background: #e3eff0; border-radius: 14px; padding: 12px 16px; max-width: 80%; }
  .rodape { position: fixed; left: 0; right: 0; bottom: 0; padding: 18px 24px 170px; background: linear-gradient(transparent, #f4f6f5 30%); }
  #prompt-textarea { max-width: 820px; margin: 0 auto; min-height: 64px; background: #fff; border: 1px solid #c9d3cf; border-radius: 16px; padding: 16px 18px; outline: none; }`;
const CHAT = `<!doctype html><meta charset="utf-8"><title>Assistente de IA</title><style>${ESTILO}</style>
<header>Assistente de IA <small>página de demonstração</small></header>
<main><div class="ia">Olá! Em que posso ajudar hoje?</div><div id="conversa"></div></main>
<div class="rodape"><div id="prompt-textarea" contenteditable="true"></div></div>`;
const VITRINE = (imagem) => `<!doctype html><meta charset="utf-8"><style>
  body { margin: 0; width: 1280px; height: 800px; display: grid; grid-template-columns: 1fr 420px; align-items: center; gap: 48px;
    padding: 0 96px; box-sizing: border-box; background: #234e52; color: #fff; font: 18px/1.5 system-ui, "Segoe UI", sans-serif; }
  h1 { font-size: 44px; line-height: 1.15; margin: 0 0 18px; } p { margin: 0 0 12px; color: #d8ecec; max-width: 520px; }
  img { width: 380px; border-radius: 14px; box-shadow: 0 24px 60px rgba(0,0,0,.35); }</style>
<div><h1>Você escolhe o que esconder</h1><p>Nomes, documentos, dados financeiros, senhas e chaves, IPs e servidores internos: cada grupo tem a sua caixinha.</p>
<p>No modo Proteger, os dados viram marcadores antes de chegar à IA. Tudo roda no seu navegador.</p></div>
<img src="data:image/png;base64,${imagem}" alt="">`;

const servidor = createServer((pedido, resposta) => {
  resposta.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  resposta.end(pedido.url.startsWith("/vitrine") ? VITRINE(globalThis.imagemDoIcone || "") : CHAT);
});
await new Promise((pronto) => servidor.listen(0, "127.0.0.1", pronto));
const base = `http://127.0.0.1:${servidor.address().port}`;

const temporaria = mkdtempSync(join(tmpdir(), "veu-loja-"));
const extensao = join(temporaria, "extensao");
cpSync(join(raiz, "extensao"), extensao, { recursive: true, filter: (o) => !o.includes(join("extensao", "teste")) && !o.includes(join("extensao", "loja")) });
const manifesto = JSON.parse(readFileSync(join(extensao, "manifest.json"), "utf8"));
manifesto.content_scripts[0].matches.push("http://127.0.0.1/*");
writeFileSync(join(extensao, "manifest.json"), JSON.stringify(manifesto));

const processo = spawn(chrome, ["--headless=new", "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--no-first-run",
  "--hide-scrollbars", `--user-data-dir=${join(temporaria, "perfil")}`, ...(process.platform === "linux" ? ["--no-sandbox"] : []), "about:blank"],
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

async function abrir(url, largura = 1280, altura = 800) {
  const { targetId } = await cdp("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp("Target.attachToTarget", { targetId, flatten: true });
  await cdp("Emulation.setDeviceMetricsOverride", { width: largura, height: altura, deviceScaleFactor: 1, mobile: false }, sessionId);
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] }, sessionId);
  await cdp("Page.navigate", { url }, sessionId);
  await pausa(1300);
  return {
    avaliar: async (expressao) => (await cdp("Runtime.evaluate", { expression: expressao, awaitPromise: true, returnByValue: true }, sessionId)).result.value,
    digitar: (texto) => cdp("Input.insertText", { text: texto }, sessionId),
    enter: async () => {
      for (const type of ["keyDown", "keyUp"]) {
        await cdp("Input.dispatchKeyEvent", { type, key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: type === "keyDown" ? "\r" : undefined }, sessionId);
      }
    },
    foto: async (nome, recorte) => {
      const { data } = await cdp("Page.captureScreenshot", { format: "png", ...(recorte ? { clip: recorte } : {}) }, sessionId);
      if (nome) writeFileSync(join(destino, nome), Buffer.from(data, "base64"));
      return data;
    },
    fechar: () => cdp("Target.closeTarget", { targetId }),
  };
}

const TEXTO = "Resuma o atendimento da cliente Maria Souza (maria.souza@example.com), CPF 529.982.247-25, telefone (11) 98765-4321.";
try {
  const { id } = await cdp("Extensions.loadUnpacked", { path: extensao });
  const definir = async (preferencias) => {
    const icone = await abrir(`chrome-extension://${id}/popup.html`, 360, 700);
    await icone.avaliar(`chrome.storage.sync.set(${JSON.stringify(preferencias)})`);
    await icone.fechar();
  };

  // 1. Modo Avisar: o aviso aparece com o botão Proteger.
  await definir({ modo: "avisar" });
  const chat = await abrir(`${base}/chat`);
  await chat.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await chat.digitar(TEXTO);
  await chat.enter();
  await pausa(600);
  await chat.foto("1-aviso.png");
  await chat.fechar();

  // 2. Modo Proteger: os dados viram marcadores antes do envio.
  await definir({ modo: "proteger" });
  const chat2 = await abrir(`${base}/chat`);
  await chat2.avaliar(`document.getElementById("prompt-textarea").focus()`);
  await chat2.digitar(TEXTO);
  await chat2.enter();
  await pausa(600);
  await chat2.foto("2-protegido.png");
  await chat2.fechar();

  // 3. As caixinhas do ícone, numa vitrine 1280x800.
  const icone = await abrir(`chrome-extension://${id}/popup.html`, 360, 1000);
  const fim = await icone.avaliar(`document.getElementById("grupos").closest("section").getBoundingClientRect().bottom`);
  globalThis.imagemDoIcone = await icone.foto(null, { x: 0, y: 0, width: 360, height: Math.ceil(fim) + 14, scale: 1 });
  await icone.fechar();
  const vitrine = await abrir(`${base}/vitrine`);
  await vitrine.foto("3-caixinhas.png");
  await vitrine.fechar();
  console.log(`3 capturas em ${destino}`);
} finally {
  processo.kill();
  servidor.close();
  await pausa(300);
  try { rmSync(temporaria, { recursive: true, force: true }); } catch { /* o Chrome ainda pode estar soltando o perfil */ }
}
