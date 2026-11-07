// Gera docs/banner.png a partir de docs/banner.html num Chrome sem janela.
//   node docs/gerar-banner.mjs [caminho do chrome]
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const pasta = dirname(fileURLToPath(import.meta.url));
const chrome = [process.argv[2], process.env.CHROME, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
  .filter(Boolean).find((caminho) => existsSync(caminho));
if (!chrome) throw new Error("Chrome não encontrado: passe o caminho como argumento.");

const processo = spawn(chrome, ["--headless=new", "--remote-debugging-pipe", "--no-first-run",
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "veu-banner-"))}`, "about:blank"],
{ stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
const [, , , entrada, saida] = processo.stdio;
let id = 0;
let buffer = "";
const esperando = new Map();
saida.on("data", (pedaco) => {
  buffer += pedaco.toString("utf8");
  let fim;
  while ((fim = buffer.indexOf("\0")) !== -1) {
    const mensagem = JSON.parse(buffer.slice(0, fim));
    buffer = buffer.slice(fim + 1);
    esperando.get(mensagem.id)?.(mensagem.result);
  }
});
const cdp = (method, params = {}, sessionId) => new Promise((pronto) => {
  const numero = ++id;
  esperando.set(numero, pronto);
  entrada.write(`${JSON.stringify({ id: numero, method, params, sessionId })}\0`);
});

try {
  const { targetId } = await cdp("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp("Target.attachToTarget", { targetId, flatten: true });
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1280, height: 640, deviceScaleFactor: 1, mobile: false }, sessionId);
  await cdp("Page.navigate", { url: pathToFileURL(resolve(pasta, "banner.html")).href }, sessionId);
  await new Promise((pronto) => setTimeout(pronto, 1500));
  const { data } = await cdp("Page.captureScreenshot", { format: "png" }, sessionId);
  writeFileSync(join(pasta, "banner.png"), Buffer.from(data, "base64"));
  console.log("docs/banner.png");
} finally {
  processo.kill();
}
