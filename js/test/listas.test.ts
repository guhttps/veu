// Listas próprias (plano Pro): os mesmos casos de tests/test_listas_proprias.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import { Veu, foldKeepingPositions } from "../src/index.ts";

const TERMS = { PESSOA: ["Joana Prado"], TERMO: ["Projeto Netuno", "Acme", "Açaí Bom"] };
const CASES: [string, string][] = [
  ["A JOANA PRADO aprovou o projeto netuno.", "A [PESSOA_1] aprovou o [TERMO_1]."],
  ["Reunião do Projeto  Netuno com a Acme.", "Reunião do [TERMO_1] com a [TERMO_2]."],
  ["A AÇAI BOM chegou.", "A [TERMO_1] chegou."],
  ["Projeto Netunos, acmeo e banana ficam.", "Projeto Netunos, acmeo e banana ficam."],
];

test("listas próprias ignoram maiúsculas, acentos e espaços, com palavras inteiras", () => {
  for (const [text, expected] of CASES) {
    const result = new Veu({ terms: TERMS }).anonymize(text);
    assert.equal(result.text, expected, text);
    assert.equal(result.restore(result.text), text);
  }
});

test("a dobra das listas mantém as posições", () => {
  const text = "Ação Ü ß İ x";
  assert.equal(foldKeepingPositions(text).length, text.length);
  assert.equal(foldKeepingPositions("ÁÉÍÓÚ Çç"), "aeiou cc");
});

test("sem listas, nada muda", () => {
  assert.equal(new Veu().anonymize("Projeto Netuno").text, "Projeto Netuno");
});
