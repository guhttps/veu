// Gera o par de chaves das licenças (Ed25519), uma vez só.
//
//   node nuvem/gerar-chaves.mjs
//
// A chave privada vai para um arquivo no seu perfil (fora do repositório), e a pública entra na extensão
// (extensao/licenca.js) e no servidor (nuvem/wrangler.toml). Depois, mande a privada para a Cloudflare:
//   npx wrangler secret put CHAVE_PRIVADA < <arquivo>
// Nunca cole a chave privada numa conversa, num commit ou num e-mail: com ela, qualquer pessoa emite licenças.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = dirname(dirname(fileURLToPath(import.meta.url)));
const pasta = join(homedir(), ".veu-licencas");
const arquivo = join(pasta, "chave-privada.txt");
const base64url = (bytes) => Buffer.from(bytes).toString("base64url");

if (existsSync(arquivo)) {
  console.error(`Já existe uma chave privada em ${arquivo}. Trocar a chave invalida todas as licenças emitidas;`
    + " se for isso mesmo, apague o arquivo antes.");
  process.exit(1);
}
const pares = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const publica = base64url(await crypto.subtle.exportKey("raw", pares.publicKey));
mkdirSync(pasta, { recursive: true });
writeFileSync(arquivo, base64url(await crypto.subtle.exportKey("pkcs8", pares.privateKey)), { mode: 0o600 });

function trocar(caminho, padrao, novo) {
  const texto = readFileSync(caminho, "utf8");
  if (!padrao.test(texto)) throw new Error(`Não achei onde colocar a chave pública em ${caminho}.`);
  writeFileSync(caminho, texto.replace(padrao, novo));
}
trocar(join(raiz, "extensao", "licenca.js"), /const CHAVE_PUBLICA = "[^"]*";/, `const CHAVE_PUBLICA = "${publica}";`);
trocar(join(raiz, "nuvem", "wrangler.toml"), /CHAVE_PUBLICA = "[^"]*"/, `CHAVE_PUBLICA = "${publica}"`);

console.log(`Chave pública: ${publica} (já está em extensao/licenca.js e em nuvem/wrangler.toml)`);
console.log(`Chave privada: ${arquivo}`);
console.log("Próximo passo, dentro da pasta nuvem:");
console.log(`  npx wrangler secret put CHAVE_PRIVADA < "${arquivo}"`);
