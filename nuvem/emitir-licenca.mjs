// Emite uma licença à mão (plano Empresa, cortesia ou teste), com a chave privada de nuvem/gerar-chaves.mjs.
//
//   node nuvem/emitir-licenca.mjs --plano empresa --pessoas 10 --email ti@empresa.example --dias 31
//
// Licenças à mão não renovam sozinhas: emita outra quando o pagamento seguinte chegar.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";

import { assinar } from "./worker.js";

const { values } = parseArgs({
  options: {
    plano: { type: "string", default: "pro" },
    email: { type: "string", default: "" },
    dias: { type: "string", default: "31" },
    pessoas: { type: "string" },
    chave: { type: "string", default: join(homedir(), ".veu-licencas", "chave-privada.txt") },
  },
});
if (!["pro", "empresa"].includes(values.plano)) {
  console.error('O plano precisa ser "pro" ou "empresa".');
  process.exit(1);
}
const privada = await crypto.subtle.importKey("pkcs8", Buffer.from(readFileSync(values.chave, "utf8").trim(), "base64url"),
  { name: "Ed25519" }, false, ["sign"]);
const agora = Math.floor(Date.now() / 1000);
const licenca = { v: 1, plano: values.plano, email: values.email, assinatura: `manual-${agora}`, emitida: agora,
  exp: agora + Number(values.dias) * 86400, ...(values.pessoas ? { pessoas: Number(values.pessoas) } : {}) };
console.log(await assinar(licenca, privada));
