// Servidor de licenças do Véu Pro (Cloudflare Workers). Não guarda nada e nunca recebe textos: só o retorno do
// Mercado Pago depois do pagamento e, na renovação, a própria chave da pessoa.
//
//   GET  /pronto?preapproval_id=...   página de volta do Mercado Pago: confere o pagamento e mostra a chave
//   POST /renovar  {"chave": "VEU1..."} chave nova enquanto a assinatura estiver ativa
//
// Variáveis (wrangler.toml): CHAVE_PUBLICA e PLANOS ({"id do plano no Mercado Pago": {"plano": "pro", "nome": "..."}}).
// Segredos (npx wrangler secret put): CHAVE_PRIVADA (nuvem/gerar-chaves.mjs) e MP_TOKEN (access token do Mercado Pago).

export const PREFIXO = "VEU1.";
const MERCADO_PAGO = "https://api.mercadopago.com";
const DIA = 86400;
const CORS = { "access-control-allow-origin": "*", "access-control-allow-methods": "POST, OPTIONS",
  "access-control-allow-headers": "content-type" };

export const paraBase64url = (bytes) =>
  btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const deBase64url = (texto) =>
  Uint8Array.from(atob(texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4)),
    (char) => char.charCodeAt(0));

/** Assina os dados da licença: "VEU1.<dados>.<assinatura>". */
export async function assinar(licenca, chavePrivada) {
  const dados = paraBase64url(new TextEncoder().encode(JSON.stringify(licenca)));
  const assinatura = await crypto.subtle.sign({ name: "Ed25519" }, chavePrivada, new TextEncoder().encode(PREFIXO + dados));
  return `${PREFIXO}${dados}.${paraBase64url(assinatura)}`;
}

/** Dados de uma chave com assinatura válida (vencida ou não), ou null. */
export async function abrir(chave, chavePublica) {
  const partes = String(chave || "").trim().split(".");
  if (partes.length !== 3 || `${partes[0]}.` !== PREFIXO || chave.length > 4000) return null;
  try {
    const ok = await crypto.subtle.verify({ name: "Ed25519" }, chavePublica, deBase64url(partes[2]),
      new TextEncoder().encode(`${partes[0]}.${partes[1]}`));
    return ok ? JSON.parse(new TextDecoder().decode(deBase64url(partes[1]))) : null;
  } catch {
    return null;
  }
}

const chavePrivada = (env) => crypto.subtle.importKey("pkcs8", deBase64url(env.CHAVE_PRIVADA), { name: "Ed25519" }, false,
  ["sign"]);
const chavePublica = (env) => crypto.subtle.importKey("raw", deBase64url(env.CHAVE_PUBLICA), { name: "Ed25519" }, false,
  ["verify"]);
const planos = (env) => (typeof env.PLANOS === "string" ? JSON.parse(env.PLANOS || "{}") : env.PLANOS || {});

async function assinaturaNoMercadoPago(env, id) {
  if (!/^[A-Za-z0-9-]{6,64}$/.test(id || "")) return null;
  const resposta = await fetch(`${MERCADO_PAGO}/preapproval/${id}`, { headers: { authorization: `Bearer ${env.MP_TOKEN}` } });
  return resposta.ok ? resposta.json() : null;
}

/** Licença para uma assinatura ativa de um plano conhecido, válida até a próxima cobrança mais 5 dias. */
function licencaDe(assinatura, env, agora) {
  const plano = planos(env)[assinatura?.preapproval_plan_id];
  if (!plano || assinatura.status !== "authorized") return null;
  const proxima = Date.parse(assinatura.next_payment_date || "") / 1000;
  const segundos = Math.floor(agora / 1000);
  const exp = Number.isFinite(proxima) && proxima > segundos ? proxima + 5 * DIA : segundos + 35 * DIA;
  return { v: 1, plano: plano.plano || "pro", email: String(assinatura.payer_email || ""), assinatura: assinatura.id,
    emitida: segundos, exp: Math.min(Math.floor(exp), segundos + 400 * DIA) };
}

const json = (dados, status = 200) => new Response(JSON.stringify(dados), {
  status, headers: { "content-type": "application/json; charset=utf-8", ...CORS } });

const escapar = (texto) => String(texto).replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);

function pagina(titulo, corpo, status = 200) {
  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapar(titulo)}</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;color:#15201e}
textarea{width:100%;font:13px ui-monospace,monospace;padding:.6rem;border:1px solid #c9d6d3;border-radius:8px}
button{font:600 15px system-ui;padding:.6rem 1rem;border:0;border-radius:8px;background:#234e52;color:#fff;cursor:pointer}
ol li{margin:.3rem 0}</style></head><body><h1>${escapar(titulo)}</h1>${corpo}</body></html>`;
  return new Response(html, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
    "referrer-policy": "no-referrer", "x-content-type-options": "nosniff" } });
}

async function pronto(url, env, agora) {
  const id = url.searchParams.get("preapproval_id");
  const assinatura = await assinaturaNoMercadoPago(env, id);
  const licenca = licencaDe(assinatura, env, agora);
  if (!licenca) {
    const situacao = assinatura?.status ? ` (situação no Mercado Pago: ${escapar(assinatura.status)})` : "";
    return pagina("Ainda não confirmamos o pagamento", `<p>O Mercado Pago ainda não confirmou a assinatura${situacao}.
Atualize esta página em alguns minutos. Se o problema continuar, responda o e-mail do Mercado Pago ou abra um pedido em
<a href="https://github.com/guhttps/veu/issues">github.com/guhttps/veu</a>.</p>`, 402);
  }
  const chave = await assinar(licenca, await chavePrivada(env));
  return pagina("Pronto: o seu Véu Pro está ativo", `<p>Esta é a sua chave. Ela renova sozinha enquanto a assinatura estiver ativa.</p>
<textarea id="chave" rows="5" readonly>${escapar(chave)}</textarea>
<p><button id="copiar">Copiar a chave</button> <span id="ok" role="status"></span></p>
<ol><li>Clique no ícone do Véu, ao lado da barra de endereço.</li><li>Em <b>Véu Pro</b>, cole a chave e clique em <b>Ativar</b>.</li></ol>
<p>Guarde a chave: ela também ativa o Véu Pro em outro navegador.</p>
<script>document.getElementById("copiar").onclick=()=>navigator.clipboard.writeText(document.getElementById("chave").value)
.then(()=>{document.getElementById("ok").textContent="Copiada."});</script>`);
}

async function renovar(request, env, agora) {
  let pedido;
  try {
    const corpo = await request.text();
    if (corpo.length > 8000) return json({ erro: "Pedido grande demais." }, 413);
    pedido = JSON.parse(corpo);
  } catch {
    return json({ erro: "Envie um JSON com a chave." }, 400);
  }
  const atual = await abrir(pedido?.chave, await chavePublica(env));
  if (!atual) return json({ erro: "Chave inválida." }, 400);
  if (String(atual.assinatura).startsWith("manual")) {
    return json({ erro: "Esta chave foi emitida à mão: para renovar, fale com o suporte." }, 409);
  }
  const assinatura = await assinaturaNoMercadoPago(env, atual.assinatura);
  const licenca = licencaDe(assinatura, env, agora);
  if (!licenca) {
    return json({ erro: `A assinatura não está ativa${assinatura?.status ? ` (situação: ${assinatura.status})` : ""}.` }, 402);
  }
  if (!licenca.email) licenca.email = atual.email || "";
  return json({ chave: await assinar(licenca, await chavePrivada(env)) });
}

export default {
  async fetch(request, env, _ctx, agora = Date.now()) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (url.pathname === "/pronto" && request.method === "GET") return pronto(url, env, agora);
    if (url.pathname === "/renovar" && request.method === "POST") return renovar(request, env, agora);
    if (url.pathname === "/" && request.method === "GET") return json({ servico: "licenças do Véu Pro" });
    return json({ erro: "Endereço desconhecido." }, 404);
  },
};
