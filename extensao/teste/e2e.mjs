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

import servidorDeLicencas, { assinar, paraBase64url } from "../../nuvem/worker.js";

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

// Servidor de licenças de verdade (nuvem/worker.js) rodando aqui, com um par de chaves de teste, os planos e preços do
// wrangler.toml e um Mercado Pago falso. A extensão e a página conferem as chaves com a chave pública de teste e falam
// com este servidor: dá para simular compra, ativação, renovação e mudança de preço sem dinheiro de verdade.
const parDeTeste = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const PUBLICA_DE_TESTE = paraBase64url(await crypto.subtle.exportKey("raw", parDeTeste.publicKey));
const wrangler = readFileSync(join(raiz, "nuvem", "wrangler.toml"), "utf8");
const variavel = (nome) => new RegExp(`^${nome} = '(.*)'$`, "m").exec(wrangler)[1];
const ambiente = {
  CHAVE_PRIVADA: paraBase64url(await crypto.subtle.exportKey("pkcs8", parDeTeste.privateKey)),
  CHAVE_PUBLICA: PUBLICA_DE_TESTE, MP_TOKEN: "token-de-teste", PLANOS: variavel("PLANOS"), PAGAMENTOS: variavel("PAGAMENTOS"),
};
const agoraEmSegundos = Math.floor(Date.now() / 1000);
const CHAVE_DE_TESTE = await assinar({ v: 1, plano: "pro", email: "teste@example.com", assinatura: "manual-e2e",
  emitida: agoraEmSegundos, exp: agoraEmSegundos + 86400 }, parDeTeste.privateKey);
const dadosDaChave = (chave) => JSON.parse(Buffer.from(String(chave).split(".")[1], "base64url").toString());

const mp = { preferencias: [], pagamentos: [], assinaturas: new Map() };
const fetchDeVerdade = globalThis.fetch;
globalThis.fetch = async (url, opcoes = {}) => {
  const endereco = String(url);
  if (!endereco.startsWith("https://api.mercadopago.com")) return fetchDeVerdade(url, opcoes);
  if (endereco.endsWith("/checkout/preferences")) {
    const preferencia = { ...JSON.parse(opcoes.body), id: `SIM-${mp.preferencias.length + 1}` };
    mp.preferencias.push(preferencia);
    return Response.json({ id: preferencia.id,
      init_point: `https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=${preferencia.id}` });
  }
  const busca = /\/v1\/payments\/search\?(.*)$/.exec(endereco);
  if (busca) {
    const referencia = new URLSearchParams(busca[1]).get("external_reference");
    return Response.json({ results: mp.pagamentos.filter((pagamento) => pagamento.external_reference === referencia) });
  }
  const um = /\/v1\/payments\/(\d+)$/.exec(endereco);
  const pagamento = um && mp.pagamentos.find((item) => String(item.id) === um[1]);
  if (pagamento) return Response.json(pagamento);
  const assinatura = /\/preapproval\/([A-Za-z0-9-]+)$/.exec(endereco);
  if (assinatura && mp.assinaturas.has(assinatura[1])) return Response.json(mp.assinaturas.get(assinatura[1]));
  return new Response("{}", { status: 404 });
};
/** Quem compra paga a última cobrança criada: Pix aprovado na hora ou boleto ainda pendente. */
function pagarUltimaCobranca({ status = "approved", tipo = "bank_transfer" } = {}) {
  const preferencia = mp.preferencias.at(-1);
  const agora = new Date().toISOString();
  const pagamento = { id: 900000000 + mp.pagamentos.length, status, currency_id: "BRL",
    transaction_amount: preferencia.items[0].unit_price, date_created: agora, date_approved: status === "approved" ? agora : null,
    external_reference: preferencia.external_reference, payer: { email: "cliente@example.com" }, payment_type_id: tipo };
  mp.pagamentos.push(pagamento);
  return { preferencia, pagamento };
}

const licencas = createServer(async (pedido, resposta) => {
  const partes = [];
  for await (const parte of pedido) partes.push(parte);
  const request = new Request(`http://127.0.0.1:${licencas.address().port}${pedido.url}`, {
    method: pedido.method, headers: { "content-type": pedido.headers["content-type"] || "text/plain" },
    body: ["GET", "HEAD", "OPTIONS"].includes(pedido.method) ? undefined : Buffer.concat(partes),
  });
  const respostaDoServidor = await servidorDeLicencas.fetch(request, ambiente, {});
  resposta.writeHead(respostaDoServidor.status, Object.fromEntries(respostaDoServidor.headers));
  resposta.end(Buffer.from(await respostaDoServidor.arrayBuffer()));
});
await new Promise((pronto) => licencas.listen(0, "127.0.0.1", pronto));
const SERVIDOR_DE_TESTE = `http://127.0.0.1:${licencas.address().port}`;
const LICENCA_JS = readFileSync(join(raiz, "extensao", "licenca.js"), "utf8")
  .replace(/const CHAVE_PUBLICA = "[^"]*"/, `const CHAVE_PUBLICA = "${PUBLICA_DE_TESTE}"`)
  .replace(/const SERVIDOR = "[^"]*"/, `const SERVIDOR = "${SERVIDOR_DE_TESTE}"`);
const noServidor = async (caminho, opcoes = {}) => {
  const resposta = await fetchDeVerdade(`${SERVIDOR_DE_TESTE}${caminho}`, { redirect: "manual", ...opcoes });
  return { status: resposta.status, local: resposta.headers.get("location"), html: await resposta.text() };
};
const chaveNaPagina = (html) => /VEU1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/.exec(html)?.[0];

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
const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".png": "image/png" };
const servidor = createServer((pedido, resposta) => {
  const caminho = new URL(pedido.url, "http://x").pathname;
  if (caminho === "/chat") {
    resposta.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return resposta.end(CHAT);
  }
  if (caminho === "/web/licenca.js") { // a conferência da chave com a chave pública de teste
    resposta.writeHead(200, { "content-type": "text/javascript" });
    return resposta.end(LICENCA_JS);
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
writeFileSync(join(extensao, "licenca.js"), LICENCA_JS);

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
  await icone.avaliar(`document.getElementById("pro-chave").value = ${JSON.stringify(CHAVE_DE_TESTE)}`);
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

// Os planos de hoje, de ponta a ponta: compra por Pix, ativação no ícone, aumento de preço, pagar mais um período pelo
// ícone (preço guardado e dias somados), quem chega depois, boleto, recuperar a chave e assinatura que renova sozinha.
async function testarPlanos(id) {
  const precos = JSON.parse(ambiente.PAGAMENTOS);
  const reais = (valor) => `R$ ${valor.toFixed(2).replace(".", ",")}`;

  const compra = await noServidor("/comprar?periodo=mensal");
  const primeira = mp.preferencias.at(-1);
  confere(compra.status === 303 && /^https:\/\/www\.mercadopago\.com\.br\//.test(compra.local)
    && primeira.items[0].unit_price === precos.mensal.valor
    && JSON.stringify(primeira.payment_methods.excluded_payment_types) === '[{"id":"ticket"}]',
  `plano de 1 mês: cobrança de ${reais(precos.mensal.valor)} no Mercado Pago, sem boleto`);
  pagarUltimaCobranca();
  const depoisDoPix = await noServidor(`/pago?ref=${primeira.external_reference}`);
  const chaveMensal = chaveNaPagina(depoisDoPix.html);
  confere(depoisDoPix.status === 200 && Boolean(chaveMensal), "depois do Pix, a página de volta mostra a chave");

  const icone = await abrir(`chrome-extension://${id}/popup.html`);
  await icone.avaliar(`document.getElementById("pro-chave").value = ${JSON.stringify(chaveMensal)};
    document.getElementById("pro-botao").click()`);
  await pausa(800);
  const estado = await icone.avaliar(`[document.getElementById("pro-estado").textContent,
    document.getElementById("pro-pagar").hidden, document.getElementById("pagar-mensal").textContent]`);
  confere(/ativo até/.test(estado[0]) && !estado[1] && estado[2].includes(reais(precos.mensal.valor)),
    `chave de 1 mês ativa no ícone, com o botão "${estado[2]}"`);

  // O preço sobe: quem já paga continua no preço antigo e não perde os dias que faltavam.
  ambiente.PAGAMENTOS = JSON.stringify({ ...precos, mensal: { ...precos.mensal, valor: 14.9 }, anual: { ...precos.anual, valor: 149 } });
  const cobrancasAntes = mp.preferencias.length;
  await icone.avaliar(`document.getElementById("pagar-mensal").click()`);
  let renovacao;
  for (let tentativa = 0; tentativa < 20 && !renovacao; tentativa++) {
    await pausa(200);
    if (mp.preferencias.length > cobrancasAntes) renovacao = mp.preferencias.at(-1);
  }
  confere(renovacao?.items[0].unit_price === precos.mensal.valor,
    `com o preço novo (R$ 14,90), o ícone cobra ${renovacao ? reais(renovacao.items[0].unit_price) : "nada"} de quem já paga`);
  await pausa(500);
  const { targetInfos } = await cdp("Target.getTargets");
  const abaDoPagamento = renovacao && targetInfos.find((alvo) => alvo.url.includes(`pref_id=${renovacao.id}`));
  confere(Boolean(abaDoPagamento), "o pagamento abre numa aba do Mercado Pago");
  if (abaDoPagamento) await cdp("Target.closeTarget", { targetId: abaDoPagamento.targetId });
  if (renovacao) {
    pagarUltimaCobranca();
    const renovada = chaveNaPagina((await noServidor(`/pago?ref=${renovacao.external_reference}`)).html);
    confere(Boolean(renovada) && dadosDaChave(renovada).exp === dadosDaChave(chaveMensal).exp + 30 * 86400,
      "o mês novo começa quando o anterior acaba (nenhum dia perdido)");
  }
  await noServidor("/comprar?periodo=anual");
  const novoCliente = mp.preferencias.at(-1);
  confere(novoCliente.items[0].unit_price === 149 && novoCliente.payment_methods.installments === 12,
    "quem chega depois paga o preço novo (1 ano por R$ 149,00, em até 12 vezes)");
  ambiente.PAGAMENTOS = JSON.stringify(precos);

  // Boleto: a página espera; compensado, a chave volta pelo número da operação e o e-mail.
  await noServidor("/comprar?periodo=anual");
  const { preferencia: doBoleto, pagamento: boleto } = pagarUltimaCobranca({ status: "pending", tipo: "ticket" });
  const esperando = await noServidor(`/pago?ref=${doBoleto.external_reference}`);
  confere(esperando.status === 202 && !chaveNaPagina(esperando.html) && esperando.html.includes("http-equiv=\"refresh\""),
    "boleto ainda não pago: a página espera e se atualiza, sem chave");
  boleto.status = "approved";
  boleto.date_approved = new Date().toISOString();
  const recuperada = await noServidor("/recuperar", { method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" }, body: `operacao=${boleto.id}&email=cliente%40example.com` });
  confere(Boolean(chaveNaPagina(recuperada.html)), "boleto compensado: a chave volta pelo número da operação e o e-mail");

  // Assinatura no cartão: a chave vem de /pronto e, perto do vencimento, a extensão renova sozinha.
  const [planoMensal] = Object.keys(JSON.parse(ambiente.PLANOS));
  const daqui = (dias) => new Date(Date.now() + dias * 86400000).toISOString();
  mp.assinaturas.set("assinatura-e2e", { id: "assinatura-e2e", status: "authorized", preapproval_plan_id: planoMensal,
    payer_email: "cliente@example.com", next_payment_date: daqui(1) });
  const daAssinatura = chaveNaPagina((await noServidor("/pronto?preapproval_id=assinatura-e2e")).html);
  confere(Boolean(daAssinatura), "assinatura no cartão: a página de volta mostra a chave");
  mp.assinaturas.get("assinatura-e2e").next_payment_date = daqui(31); // o Mercado Pago cobrou o mês seguinte
  await icone.avaliar(`document.getElementById("pro-chave").value = ${JSON.stringify(daAssinatura)};
    document.getElementById("pro-botao").click()`);
  let guardada = daAssinatura;
  for (let tentativa = 0; tentativa < 20 && guardada === daAssinatura; tentativa++) {
    await pausa(250);
    await icone.avaliar(`chrome.runtime.sendMessage({ tipo: "configuracao" })`);
    guardada = await icone.avaliar(`chrome.storage.local.get("licenca").then((itens) => itens.licenca)`);
  }
  confere(guardada !== daAssinatura && dadosDaChave(guardada).exp > dadosDaChave(daAssinatura).exp + 20 * 86400,
    "assinatura: perto do vencimento, a extensão renova a chave sozinha");
  confere(await icone.avaliar(`document.getElementById("pro-pagar").hidden`) === true,
    "a assinatura não mostra os botões de pagar por período");
  await icone.fechar();

  // A página web aceita a chave paga por período e libera o Pro.
  const pagina = await abrir(`${base}/web/index.html?lang=pt`);
  await pagina.avaliar(`document.getElementById("pro").open = true;
    document.getElementById("pro-chave").value = ${JSON.stringify(chaveMensal)}; document.getElementById("pro-botao").click()`);
  await pausa(500);
  confere(/ativo até/.test(await pagina.avaliar(`document.getElementById("pro-estado").textContent`)),
    "a chave paga por período também ativa o Pro na página");
  await pagina.fechar();
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

  // Arquivos inteiros na página: grátis, um por vez, com o mesmo cofre do texto.
  const { writeZip, readZip } = await import("../../js/dist/index.js").then((m) => m.default ?? m);
  const baixados = join(temporaria, "baixados");
  await cdp("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: baixados });
  const xmlDoWord = async (caminho) => new TextDecoder().decode((await readZip(new Uint8Array(readFileSync(caminho)))).get("word/document.xml"));
  const WORD = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
  const docs = await abrir(`${base}/web/index.html?lang=pt`);
  const proposta = join(temporaria, "proposta.docx");
  writeFileSync(proposta, await writeZip(new Map([["word/document.xml", new TextEncoder().encode(
    `<w:document ${WORD}><w:body><w:p><w:r><w:t>Contratada Maria Souza, CPF ${CPF}</w:t></w:r></w:p></w:body></w:document>`)]])));
  await enviarArquivo(docs, "#arquivo-proteger", proposta);
  const propostaProtegida = join(baixados, "proposta-protegido.docx");
  const xmlProtegido = (await esperarArquivo(propostaProtegida)) ? await xmlDoWord(propostaProtegida) : "";
  confere(xmlProtegido.includes("[PESSOA_1]") && xmlProtegido.includes("[CPF_1]") && !xmlProtegido.includes("Souza"),
    `a página protege um Word inteiro (${xmlProtegido.slice(-90)})`);
  await docs.avaliar(`document.getElementById("resposta").focus()`);
  await docs.digitar("A contratada é [PESSOA_1].");
  await pausa(200);
  const respostaDoArquivo = await docs.avaliar(`document.getElementById("restaurado").textContent`);
  confere(respostaDoArquivo === "A contratada é Maria Souza.", `a resposta sobre o arquivo volta no passo 3 (${respostaDoArquivo})`);
  await enviarArquivo(docs, "#arquivo-devolver", propostaProtegida);
  const propostaDeVolta = join(baixados, "proposta-com-dados.docx");
  const xmlDeVolta = (await esperarArquivo(propostaDeVolta)) ? await xmlDoWord(propostaDeVolta) : "";
  confere(xmlDeVolta.includes(`Maria Souza, CPF ${CPF}`), "a página devolve os dados reais ao Word");
  const exame = join(temporaria, "exame.pdf");
  writeFileSync(exame, pdfCom(`Paciente Maria Souza, CPF ${CPF}`));
  await enviarArquivo(docs, "#arquivo-proteger", exame);
  const exameProtegido = join(baixados, "exame-protegido.txt");
  const textoDoExame = (await esperarArquivo(exameProtegido)) ? readFileSync(exameProtegido, "utf8") : "";
  confere(textoDoExame.includes("[PESSOA_1]") && textoDoExame.includes("[CPF_1]") && !textoDoExame.includes("Souza"),
    `a página lê o PDF com o pdf.js e protege o texto (${textoDoExame.replace(/\n/g, " ").slice(0, 70)})`);
  // Dois arquivos de uma vez no grátis: só o primeiro.
  const soltarDois = (nomes) => docs.avaliar(`(() => {
    const dados = new DataTransfer();
    for (const nome of ${JSON.stringify(nomes)}) dados.items.add(new File(["Cliente Maria Souza, CPF ${CPF}"], nome, { type: "text/plain" }));
    document.getElementById("soltar-proteger").dispatchEvent(new DragEvent("drop", { dataTransfer: dados, bubbles: true, cancelable: true }));
  })()`);
  await soltarDois(["lote-a.txt", "lote-b.txt"]);
  const primeiro = await esperarArquivo(join(baixados, "lote-a-protegido.txt"));
  await pausa(600);
  const aviso = await docs.avaliar(`document.getElementById("arquivos-feitos").textContent`);
  confere(primeiro && !existsSync(join(baixados, "lote-b-protegido.txt")) && /Véu Pro/.test(aviso),
    "no grátis, a página protege um arquivo por vez");

  // Véu Pro na página: a chave é conferida aqui mesmo, e libera vários arquivos e as listas próprias.
  {
    await docs.avaliar(`document.getElementById("pro").open = true; document.getElementById("pro-chave").value = ${JSON.stringify(CHAVE_DE_TESTE)}`);
    await docs.avaliar(`document.getElementById("pro-botao").click()`);
    await pausa(500);
    const estadoPro = await docs.avaliar(`document.getElementById("pro-estado").textContent`);
    confere(/ativo até/.test(estadoPro), `a chave do Pro ativa na página (${estadoPro.slice(0, 40)})`);
    await docs.avaliar(`document.getElementById("lista-nomes").value = "Joana Prado"; document.getElementById("salvar-listas").click()`);
    await pausa(400);
    await docs.avaliar(`(() => { const e = document.getElementById("entrada"); e.value = "Fale com a JOANA PRADO amanhã."; e.dispatchEvent(new Event("input")); })()`);
    await pausa(500);
    const comLista = await docs.avaliar(`document.getElementById("saida").textContent`);
    confere(!/joana/i.test(comLista) && /\[PESSOA_\d+\]/.test(comLista), `a lista própria vale na página (${comLista})`);
    await soltarDois(["pro-a.txt", "pro-b.txt"]);
    const doisBaixados = (await esperarArquivo(join(baixados, "pro-a-protegido.txt"))) && (await esperarArquivo(join(baixados, "pro-b-protegido.txt")));
    confere(doisBaixados, "com o Pro, a página protege vários arquivos de uma vez");
    await docs.avaliar(`document.getElementById("pro-remover").click()`);
    await pausa(300);
  }
  await docs.fechar();

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

  // Véu Pro, com uma chave de teste do servidor de licenças local, e os planos de ponta a ponta.
  await testarPro(id);
  await testarPlanos(id);
} catch (erro) {
  falhas += 1;
  console.error(erro);
} finally {
  processo.kill();
  servidor.close();
  licencas.close();
  await pausa(500);
  try {
    rmSync(temporaria, { recursive: true, force: true });
  } catch { /* o Chrome ainda pode estar soltando o perfil */ }
}
console.log(falhas ? `\n${falhas} falha(s)` : "\nTudo certo.");
process.exit(falhas ? 1 : 0);
