// A versão JavaScript precisa detectar e anonimizar exatamente como a versão em Python.
// Os casos vêm de scripts/gerar_conformidade.py (rode-o depois de mudar um detector).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { Veu } from "../src/index.ts";

interface Case {
  texto: string;
  entidades: [string, number, number, number][];
  anonimizado: string;
  mascarado: string;
  generalizado?: string;
}

const { casos } = JSON.parse(readFileSync(new URL("./conformidade.json", import.meta.url), "utf8")) as { casos: Case[] };
const veu = new Veu();
const masker = veu.withOperator("mascara");
const generalizer = veu.withOperator("generalizar");

test(`conformidade com o Python: ${casos.length} casos`, () => {
  const failures: string[] = [];
  for (const item of casos) {
    const found = veu.analyze(item.texto).map((e) => [e.label, e.start, e.end, e.score]);
    const expected = item.entidades;
    const same = found.length === expected.length && found.every((e, i) =>
      e[0] === expected[i][0] && e[1] === expected[i][1] && e[2] === expected[i][2]
      && Math.abs((e[3] as number) - expected[i][3]) < 1e-9);
    if (!same) {
      failures.push(`${JSON.stringify(item.texto)}\n  python: ${JSON.stringify(expected)}\n  js:     ${JSON.stringify(found)}`);
      continue;
    }
    if (veu.anonymize(item.texto).text !== item.anonimizado) failures.push(`anonimizado difere: ${item.texto}`);
    if (masker.anonymize(item.texto).text !== item.mascarado) failures.push(`mascarado difere: ${item.texto}`);
    if (item.generalizado !== undefined && generalizer.anonymize(item.texto).text !== item.generalizado) {
      failures.push(`generalizado difere: ${item.texto}`);
    }
  }
  assert.deepEqual(failures.slice(0, 10), [], `${failures.length} casos diferentes`);
});
