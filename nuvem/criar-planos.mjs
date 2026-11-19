// Cria os planos de assinatura do Véu Pro no Mercado Pago (uma vez só) e grava os ids em nuvem/wrangler.toml.
//
//   PowerShell:  $env:MP_TOKEN = "<access token>"; node nuvem/criar-planos.mjs https://<seu-servidor>.workers.dev
//
// O access token fica só na variável de ambiente desta janela: não o cole em conversas nem em arquivos.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = dirname(dirname(fileURLToPath(import.meta.url)));
const servidor = (process.argv[2] || "").replace(/\/+$/, "");
const token = process.env.MP_TOKEN;
if (!token || !/^https:\/\/[\w.-]+$/.test(servidor)) {
  console.error("Uso: defina MP_TOKEN e passe o endereço do servidor: node nuvem/criar-planos.mjs https://...workers.dev");
  process.exit(1);
}

const PLANOS = [
  { nome: "Véu Pro mensal", frequencia: 1, valor: 9.9 },
  { nome: "Véu Pro anual", frequencia: 12, valor: 99 },
];
const criados = {};
for (const plano of PLANOS) {
  const resposta = await fetch("https://api.mercadopago.com/preapproval_plan", {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({
      reason: plano.nome,
      auto_recurring: { frequency: plano.frequencia, frequency_type: "months", transaction_amount: plano.valor,
        currency_id: "BRL" },
      back_url: `${servidor}/pronto`,
    }),
  });
  const dados = await resposta.json();
  if (!resposta.ok) {
    console.error(`O Mercado Pago recusou o plano "${plano.nome}": ${dados.message || resposta.status}`);
    process.exit(1);
  }
  criados[dados.id] = { plano: "pro", nome: plano.nome };
  console.log(`${plano.nome}: ${dados.init_point}`);
}

const caminho = join(raiz, "nuvem", "wrangler.toml");
const texto = readFileSync(caminho, "utf8");
writeFileSync(caminho, texto.replace(/PLANOS = '[^']*'/, `PLANOS = '${JSON.stringify(criados)}'`));
console.log("Os ids dos planos estão em nuvem/wrangler.toml. Os links acima são os botões de assinar da página de planos.");
