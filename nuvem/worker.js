// Servidor de licenças do Véu Pro (Cloudflare Workers). Não guarda nada e nunca recebe textos: só o retorno do
// Mercado Pago depois do pagamento e, na renovação, a própria chave da pessoa.
//
// Assinatura (cartão de crédito, renova sozinha):
//   GET  /pronto?preapproval_id=...   página de volta do Mercado Pago: confere a assinatura e mostra a chave
//   POST /renovar  {"chave": "VEU1..."} chave nova enquanto a assinatura estiver ativa
// Pagamento avulso (Pix, boleto, cartão, saldo ou parcelado do Mercado Pago; vale um período):
//   GET  /comprar?periodo=mensal       cria a cobrança no Mercado Pago com uma referência aleatória e leva até ela
//   GET  /pago?ref=...                 página de volta: confere o pagamento daquela referência e mostra a chave
//   GET|POST /recuperar                chave de novo, com o número da operação e o e-mail do pagamento
//   GET|POST /renovar-periodo          mais um período com a chave atual: mantém o preço da primeira compra e soma os
//                                      dias que faltavam (JSON da extensão ou formulário da página)
//
// Variáveis (wrangler.toml): CHAVE_PUBLICA, PLANOS ({"id do plano no Mercado Pago": {"plano": "pro", "nome": "..."}})
// e PAGAMENTOS ({"mensal": {"plano": "pro", "nome": "...", "valor": 9.9, "dias": 30, "parcelas": 1, "excluir": ["ticket"]}}).
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
const lerJson = (valor) => (typeof valor === "string" ? JSON.parse(valor || "{}") : valor || {});
const planos = (env) => lerJson(env.PLANOS);
const pagamentos = (env) => lerJson(env.PAGAMENTOS);
const autorizacao = (env) => ({ authorization: `Bearer ${env.MP_TOKEN}` });
const PAGINA_DE_PLANOS = "https://guhttps.github.io/veu/planos.html";

async function assinaturaNoMercadoPago(env, id) {
  if (!/^[A-Za-z0-9-]{6,64}$/.test(id || "")) return null;
  const resposta = await fetch(`${MERCADO_PAGO}/preapproval/${id}`, { headers: autorizacao(env) });
  return resposta.ok ? resposta.json() : null;
}

// A referência de um pagamento avulso: "<período>-<24 caracteres aleatórios>.<termos>.<assinatura>". Só quem pagou conhece
// a parte aleatória, então o endereço /pago?ref=... não dá para adivinhar. Os termos são os preços combinados (em
// centavos) e o vencimento da chave anterior, assinados pelo servidor: ninguém muda o preço mexendo no endereço.
// Referências antigas, sem termos, valem pelo preço do dia.
const REFERENCIA = /^([a-z]{3,12})-([A-Za-z0-9_-]{22,64})(?:\.([A-Za-z0-9_-]{4,200})\.([A-Za-z0-9_-]{80,90}))?$/;
// Quem paga por período mantém o preço da primeira compra se pagar mais um período até 30 dias depois do vencimento.
const TOLERANCIA_DO_PRECO = 30 * DIA;

const centavos = (valor) => Math.round(Number(valor) * 100);
const precosAtuais = (env) => Object.fromEntries(Object.entries(pagamentos(env)).map(([nome, periodo]) => [nome, centavos(periodo.valor)]));
const limparPrecos = (precos) => Object.fromEntries(Object.entries(precos && typeof precos === "object" ? precos : {})
  .filter(([nome, valor]) => /^[a-z]{3,12}$/.test(nome) && Number.isInteger(valor) && valor > 0));

async function referenciaCom(nome, termos, env) {
  const base = `${nome}-${paraBase64url(crypto.getRandomValues(new Uint8Array(18)))}`;
  const dados = paraBase64url(new TextEncoder().encode(JSON.stringify(termos)));
  const assinatura = await crypto.subtle.sign({ name: "Ed25519" }, await chavePrivada(env),
    new TextEncoder().encode(`VEUREF.${base}.${dados}`));
  return `${base}.${dados}.${paraBase64url(assinatura)}`;
}

/** Termos assinados da referência ({p: preços em centavos, e: vencimento anterior}), {} sem termos, null se adulterada. */
async function termosDe(referencia, env) {
  const partes = REFERENCIA.exec(String(referencia || ""));
  if (!partes) return null;
  if (!partes[3]) return {};
  try {
    const ok = await crypto.subtle.verify({ name: "Ed25519" }, await chavePublica(env), deBase64url(partes[4]),
      new TextEncoder().encode(`VEUREF.${partes[1]}-${partes[2]}.${partes[3]}`));
    return ok ? JSON.parse(new TextDecoder().decode(deBase64url(partes[3]))) : null;
  } catch {
    return null;
  }
}

function periodoDe(referencia, env) {
  const nome = REFERENCIA.exec(String(referencia || ""))?.[1];
  const tabela = pagamentos(env);
  return nome && Object.hasOwn(tabela, nome) ? { ...tabela[nome], id: nome } : null; // "nome" é o título ("Véu Pro por 1 mês")
}

/**
 * Licença para um pagamento avulso aprovado, no valor combinado: vale `dias` a partir da aprovação ou, se a chave
 * anterior ainda valia, a partir do vencimento dela. Leva os preços combinados, para a próxima vez.
 */
async function licencaDoPagamento(pagamento, env, agora) {
  const periodo = periodoDe(pagamento?.external_reference, env);
  if (!periodo || pagamento.status !== "approved" || pagamento.currency_id !== "BRL") return null;
  const termos = await termosDe(pagamento.external_reference, env);
  if (!termos) return null;
  const precos = { ...precosAtuais(env), ...limparPrecos(termos.p) };
  if (!(centavos(pagamento.transaction_amount) >= precos[periodo.id])) return null;
  const pago = Math.floor(Date.parse(pagamento.date_approved || pagamento.date_created || "") / 1000);
  if (!Number.isFinite(pago)) return null;
  const anterior = Number.isInteger(termos.e) ? Math.min(termos.e, pago + 400 * DIA) : 0;
  return { v: 1, plano: periodo.plano || "pro", email: String(pagamento.payer?.email || ""), pagamento: String(pagamento.id),
    emitida: Math.floor(agora / 1000), exp: Math.max(pago, anterior) + Math.min(Number(periodo.dias) || 30, 400) * DIA, precos };
}

/** Data de um instante (segundos) no horário de Brasília, como 19/12/2026. */
const dataBR = (segundos) => new Date((segundos - 3 * 3600) * 1000).toISOString().slice(0, 10).split("-").reverse().join("/");

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

function pagina(titulo, corpo, status = 200, cabeca = "") {
  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${cabeca}<title>${escapar(titulo)}</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;color:#15201e}
textarea,input{width:100%;box-sizing:border-box;font:14px ui-monospace,monospace;padding:.6rem;border:1px solid #c9d6d3;border-radius:8px}
button,.botao{display:inline-block;font:600 15px system-ui;padding:.6rem 1rem;border:0;border-radius:8px;background:#234e52;color:#fff;cursor:pointer;text-decoration:none}
label{display:block;margin:.8rem 0}ol li{margin:.3rem 0}.nota{color:#4b5f5b;font-size:14px}</style></head>
<body><h1>${escapar(titulo)}</h1>${corpo}</body></html>`;
  return new Response(html, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
    "referrer-policy": "no-referrer", "x-content-type-options": "nosniff" } });
}

const SUPORTE = `<a href="mailto:veu.ajuda@protonmail.com">veu.ajuda@protonmail.com</a> (ou em <a href="https://github.com/guhttps/veu/issues">github.com/guhttps/veu</a>)`;

async function paginaDaChave(licenca, env, aviso) {
  const chave = await assinar(licenca, await chavePrivada(env));
  return pagina("Pronto: o seu Véu Pro está ativo", `<p>Esta é a sua chave. ${aviso}</p>
<textarea id="chave" rows="5" readonly>${escapar(chave)}</textarea>
<p><button id="copiar">Copiar a chave</button> <span id="ok" role="status"></span></p>
<ol><li>Clique no ícone do Véu, ao lado da barra de endereço.</li><li>Em <b>Véu Pro</b>, cole a chave e clique em <b>Ativar</b>.</li></ol>
<p>Guarde a chave: ela também ativa o Véu Pro em outro navegador.</p>
<script>document.getElementById("copiar").onclick=()=>navigator.clipboard.writeText(document.getElementById("chave").value)
.then(()=>{document.getElementById("ok").textContent="Copiada."});</script>`);
}

async function pronto(url, env, agora) {
  const id = url.searchParams.get("preapproval_id");
  const assinatura = await assinaturaNoMercadoPago(env, id);
  const licenca = licencaDe(assinatura, env, agora);
  if (!licenca) {
    const situacao = assinatura?.status ? ` (situação no Mercado Pago: ${escapar(assinatura.status)})` : "";
    return pagina("Ainda não confirmamos o pagamento", `<p>O Mercado Pago ainda não confirmou a assinatura${situacao}.
Atualize esta página em alguns minutos. Se o problema continuar, escreva para ${SUPORTE}.</p>`, 402);
  }
  return paginaDaChave(licenca, env, "Ela renova sozinha enquanto a assinatura estiver ativa.");
}

const avisoDoPeriodo = (licenca, origem) => `Ela vale até ${dataBR(licenca.exp)}. Para continuar com o mesmo preço, pague
mais um período pelo ícone do Véu (em Véu Pro) ou em <a href="${origem}/renovar-periodo">${origem}/renovar-periodo</a>, até 30 dias
depois do vencimento: os dias que faltarem são somados.`;

const periodoValido = (nome, env) => /^[a-z]{3,12}$/.test(nome) && Object.hasOwn(pagamentos(env), nome);

/** Cria a cobrança avulsa no Mercado Pago (Checkout Pro) com os termos assinados; devolve o endereço dela ou "". */
async function criarCobranca(origem, env, nome, termos) {
  const periodo = pagamentos(env)[nome];
  const referencia = await referenciaCom(nome, termos, env);
  const volta = `${origem}/pago?ref=${referencia}`;
  let destino = "";
  try {
    const resposta = await fetch(`${MERCADO_PAGO}/checkout/preferences`, {
      method: "POST", headers: { ...autorizacao(env), "content-type": "application/json" },
      body: JSON.stringify({
        items: [{ id: `veu-${nome}`, title: periodo.nome, quantity: 1, unit_price: termos.p[nome] / 100, currency_id: "BRL",
          category_id: "services",
          description: `Chave do Véu Pro por ${periodo.dias} dias. Se fechar a página, recupere em ${origem}/recuperar` }],
        external_reference: referencia,
        back_urls: { success: volta, pending: volta, failure: volta },
        auto_return: "approved",
        statement_descriptor: "VEU PRO",
        payment_methods: { installments: Number(periodo.parcelas) || 1, excluded_payment_methods: [],
          excluded_payment_types: (periodo.excluir || []).map((id) => ({ id })) },
      }),
    });
    destino = resposta.ok ? (await resposta.json()).init_point || "" : "";
  } catch {
    destino = "";
  }
  return /^https:\/\/([a-z0-9-]+\.)*mercadopago\.com(\.br)?\//.test(destino) ? destino : "";
}

const mercadoPagoForaDoAr = () => pagina("O Mercado Pago não respondeu", `<p>Não consegui abrir o pagamento agora. Tente de
novo em alguns minutos. Se continuar, escreva para ${SUPORTE}.</p>`, 502);
const irPara = (destino) => new Response(null, { status: 303,
  headers: { location: destino, "cache-control": "no-store", "referrer-policy": "no-referrer" } });

/** Primeira compra por período: preço do dia, que fica guardado na chave. */
async function comprar(url, env) {
  const nome = url.searchParams.get("periodo") || "";
  if (!periodoValido(nome, env)) {
    return pagina("Período desconhecido", `<p>Escolha um período na <a href="${PAGINA_DE_PLANOS}">página de planos</a>.</p>`, 404);
  }
  const destino = await criarCobranca(url.origin, env, nome, { p: precosAtuais(env), e: 0 });
  return destino ? irPara(destino) : mercadoPagoForaDoAr();
}

function formularioDeRenovar(url, mensagem = "", status = 200) {
  return pagina("Pagar mais um período do Véu Pro", `${mensagem ? `<p role="alert"><b>${escapar(mensagem)}</b></p>` : ""}
<p>Cole a sua chave do Véu Pro. Se ela não venceu há mais de 30 dias, você paga o preço da sua primeira compra, e os dias que
faltavam são somados ao período novo.</p>
<form method="post" action="${url.origin}/renovar-periodo">
<label>Sua chave<textarea name="chave" rows="4" required spellcheck="false" placeholder="VEU1..."></textarea></label>
<p><button name="periodo" value="mensal">Pagar mais 1 mês</button> <button name="periodo" value="anual">Pagar mais 1 ano</button></p>
</form>
<p class="nota">Assinatura no cartão não precisa disto: ela renova sozinha. A chave serve só para conferir o seu preço e o
vencimento; nada fica guardado.</p>`, status);
}

/**
 * Mais um período com a chave atual (JSON da extensão ou formulário): até 30 dias depois do vencimento, valem os preços
 * guardados na chave (ou os do dia, se ficaram menores), e o período novo começa quando o anterior acaba.
 */
async function renovarPeriodo(request, url, env, agora) {
  if (request.method === "GET") return formularioDeRenovar(url);
  const ehJson = (request.headers.get("content-type") || "").includes("application/json");
  const recusar = (erro, status) => (ehJson ? json({ erro }, status) : formularioDeRenovar(url, erro, status));
  const corpo = await request.text();
  if (corpo.length > 8000) return recusar("Pedido grande demais.", 413);
  let campos;
  try {
    campos = ehJson ? JSON.parse(corpo) : Object.fromEntries(new URLSearchParams(corpo));
  } catch {
    return recusar("Pedido inválido.", 400);
  }
  const nome = String(campos?.periodo || "");
  if (!periodoValido(nome, env)) return recusar("Escolha 1 mês ou 1 ano.", 400);
  const atual = await abrir(String(campos?.chave || "").trim(), await chavePublica(env));
  if (!atual || atual.plano !== "pro") return recusar("Isto não parece uma chave do Véu Pro.", 400);
  if (atual.assinatura && !String(atual.assinatura).startsWith("manual")) {
    return recusar("Esta chave é de uma assinatura: ela renova sozinha enquanto a assinatura estiver ativa.", 409);
  }
  if (!atual.pagamento) return recusar("Esta chave foi emitida à mão: para renovar, escreva para o suporte.", 409);
  const hoje = precosAtuais(env);
  const continua = Number(atual.exp) >= Math.floor(agora / 1000) - TOLERANCIA_DO_PRECO;
  const guardados = limparPrecos(atual.precos);
  const precos = continua
    ? Object.fromEntries(Object.entries(hoje).map(([periodo, valor]) => [periodo, Math.min(valor, guardados[periodo] ?? valor)]))
    : hoje;
  const destino = await criarCobranca(url.origin, env, nome, { p: precos, e: continua ? Math.floor(Number(atual.exp)) : 0 });
  if (!destino) return ehJson ? json({ erro: "O Mercado Pago não respondeu. Tente de novo em alguns minutos." }, 502) : mercadoPagoForaDoAr();
  return ehJson ? json({ url: destino, valor: precos[nome] / 100, precoMantido: continua }) : irPara(destino);
}

const PENDENTES = new Set(["pending", "in_process", "authorized", "in_mediation"]);

/** Página de volta do pagamento avulso: chave, espera (Pix ou boleto ainda não pagos) ou recusa. */
async function pago(url, env, agora) {
  const referencia = url.searchParams.get("ref") || url.searchParams.get("external_reference") || "";
  const periodo = periodoDe(referencia, env);
  if (!periodo) return pagina("Pagamento não encontrado", `<p>Este endereço não é de um pagamento do Véu Pro.</p>`, 404);
  const busca = await fetch(`${MERCADO_PAGO}/v1/payments/search?external_reference=${encodeURIComponent(referencia)}`
    + "&sort=date_created&criteria=desc&limit=20", { headers: autorizacao(env) }).catch(() => null);
  if (!busca?.ok) {
    return pagina("O Mercado Pago não respondeu", `<p>Atualize esta página em alguns minutos.</p>`, 502,
      `<meta http-equiv="refresh" content="30">`);
  }
  const lista = ((await busca.json()).results || []).filter((pagamento) => pagamento.external_reference === referencia);
  const aprovado = (await Promise.all(lista.map((pagamento) => licencaDoPagamento(pagamento, env, agora)))).find(Boolean);
  if (aprovado && aprovado.exp > agora / 1000) return paginaDaChave(aprovado, env, avisoDoPeriodo(aprovado, url.origin));
  if (aprovado) {
    return pagina("Este período terminou", `<p>O período pago terminou em ${dataBR(aprovado.exp)}. Para continuar,
pague mais um período na <a href="${PAGINA_DE_PLANOS}">página de planos</a>.</p>`, 410);
  }
  const endereco = escapar(`${url.origin}/pago?ref=${referencia}`);
  if (lista.some((pagamento) => PENDENTES.has(pagamento.status))) {
    return pagina("Esperando o pagamento", `<p>O Mercado Pago ainda não confirmou o pagamento. Pix leva alguns segundos;
boleto, até 3 dias úteis. Esta página se atualiza sozinha.</p>
<p>Pode fechar e voltar depois por este endereço (guarde-o):<br><a href="${endereco}">${endereco}</a></p>
<p class="nota">Ou, com o boleto já pago, em <a href="${url.origin}/recuperar">${url.origin}/recuperar</a>, com o número da
operação que vem no e-mail do Mercado Pago.</p>`, 202, `<meta http-equiv="refresh" content="20">`);
  }
  const motivo = lista[0]?.status ? ` (situação: ${escapar(lista[0].status)})` : "";
  return pagina("O pagamento não foi concluído", `<p>Não encontramos um pagamento aprovado${motivo}. Se o pagamento foi
recusado, nada foi cobrado.</p><p><a class="botao" href="${url.origin}/comprar?periodo=${periodo.id}">Tentar de novo</a></p>`, 402);
}

function formularioDeRecuperar(url, mensagem = "", status = 200) {
  return pagina("Recuperar a chave do Véu Pro", `${mensagem ? `<p role="alert"><b>${escapar(mensagem)}</b></p>` : ""}
<p>Use o número da operação que está no e-mail do Mercado Pago e o e-mail usado no pagamento.</p>
<form method="post" action="${url.origin}/recuperar">
<label>Número da operação<input name="operacao" inputmode="numeric" autocomplete="off" required></label>
<label>E-mail usado no pagamento<input name="email" type="email" autocomplete="email" required></label>
<button>Mostrar a chave</button></form>
<p class="nota">Os dois servem só para esta consulta ao Mercado Pago: nada fica guardado.</p>`, status);
}

/** Chave de novo para quem fechou a página: número da operação + e-mail do pagamento, conferidos no Mercado Pago. */
async function recuperar(request, url, env, agora) {
  if (request.method === "GET") return formularioDeRecuperar(url);
  const corpo = await request.text();
  if (corpo.length > 2000) return formularioDeRecuperar(url, "Pedido grande demais.", 413);
  const campos = new URLSearchParams(corpo);
  const operacao = String(campos.get("operacao") || "").replace(/\D/g, "");
  const email = String(campos.get("email") || "").trim().toLowerCase();
  const naoAchei = () => formularioDeRecuperar(url,
    "Não encontramos um pagamento aprovado do Véu Pro com esse número e esse e-mail. Confira os dois no e-mail do Mercado Pago.", 404);
  if (!/^\d{6,20}$/.test(operacao) || !email.includes("@")) return naoAchei();
  const resposta = await fetch(`${MERCADO_PAGO}/v1/payments/${operacao}`, { headers: autorizacao(env) }).catch(() => null);
  const pagamento = resposta?.ok ? await resposta.json() : null;
  if (!pagamento || String(pagamento.payer?.email || "").trim().toLowerCase() !== email) return naoAchei();
  const avulsa = await licencaDoPagamento(pagamento, env, agora);
  if (avulsa) {
    return avulsa.exp > agora / 1000 ? paginaDaChave(avulsa, env, avisoDoPeriodo(avulsa, url.origin))
      : formularioDeRecuperar(url, `Esse período terminou em ${dataBR(avulsa.exp)}.`, 410);
  }
  if (periodoDe(pagamento.external_reference, env) && PENDENTES.has(pagamento.status)) {
    return formularioDeRecuperar(url, "O Mercado Pago ainda não confirmou esse pagamento. Tente de novo mais tarde.", 202);
  }
  // Cobrança de uma assinatura: a chave sai da própria assinatura, se ela estiver ativa.
  const licenca = licencaDe(await assinaturaNoMercadoPago(env, pagamento.metadata?.preapproval_id), env, agora);
  return licenca ? paginaDaChave(licenca, env, "Ela renova sozinha enquanto a assinatura estiver ativa.") : naoAchei();
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
  if (atual.pagamento && !atual.assinatura) {
    return json({ erro: "Esta chave foi paga por período e não renova sozinha: para continuar com o mesmo preço, pague mais um período pelo ícone do Véu." }, 409);
  }
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
    if (url.pathname === "/comprar" && request.method === "GET") return comprar(url, env);
    if (url.pathname === "/pago" && request.method === "GET") return pago(url, env, agora);
    if (url.pathname === "/recuperar" && ["GET", "POST"].includes(request.method)) return recuperar(request, url, env, agora);
    if (url.pathname === "/renovar-periodo" && ["GET", "POST"].includes(request.method)) {
      return renovarPeriodo(request, url, env, agora);
    }
    if (url.pathname === "/" && request.method === "GET") return json({ servico: "licenças do Véu Pro" });
    return json({ erro: "Endereço desconhecido." }, 404);
  },
};
