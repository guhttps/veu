// Gera src/data.ts a partir de src/veu/data do pacote Python: as duas versões usam as mesmas listas e regras.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const data = join(root, "..", "src", "veu", "data");

function wordlist(name) {
  const entries = [];
  for (const raw of readFileSync(join(data, name), "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (line && !line.startsWith("#")) entries.push(line);
  }
  return [...new Set(entries)];
}

const lists = {
  firstNames: wordlist("first_names.txt"),
  surnames: wordlist("surnames.txt"),
  ambiguous: wordlist("ambiguous.txt"),
  stopwords: wordlist("stopwords.txt"),
  places: wordlist("places.txt"),
  organizations: wordlist("organizations.txt"),
};
const secrets = JSON.parse(readFileSync(join(data, "segredos.json"), "utf8")).regras;

let output = "// Gerado por scripts/gerar-dados.mjs a partir de src/veu/data. Não edite à mão.\n\n";
for (const [name, values] of Object.entries(lists)) {
  output += `export const ${name}: readonly string[] = ${JSON.stringify(values)};\n\n`;
}
output += "export interface SecretRuleData {\n  id: string;\n  entidade: string;\n  padrao: string;\n  pontuacao: number;\n";
output += "  grupo?: number;\n  filtro?: string;\n  aparar?: string;\n}\n\n";
output += `export const secretRules: readonly SecretRuleData[] = ${JSON.stringify(secrets, null, 1)};\n`;
writeFileSync(join(root, "src", "data.ts"), output);
console.log(`src/data.ts: ${Object.values(lists).reduce((n, l) => n + l.length, 0)} palavras, ${secrets.length} regras`);
