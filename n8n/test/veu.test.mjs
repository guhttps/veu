// Testa o nó compilado com um IExecuteFunctions falso: esconder, restaurar, recusar e continuar em caso de erro.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const { Veu } = require("../dist/nodes/Veu/Veu.node.js");
const CPF = "529.982.247-25";

function contexto(items, parametros, { continuar = false } = {}) {
  return {
    getInputData: () => items.map((json) => ({ json })),
    getNodeParameter: (nome, indice, padrao) => {
      const valor = typeof parametros[nome] === "function" ? parametros[nome](indice) : parametros[nome];
      return valor === undefined ? padrao : valor;
    },
    getNode: () => ({ name: "Véu", type: "veu", typeVersion: 1, parameters: {} }),
    continueOnFail: () => continuar,
  };
}

test("descrição do nó", () => {
  const no = new Veu();
  assert.equal(no.description.name, "veu");
  assert.deepEqual(no.description.properties[0].options.map((o) => o.value), ["esconder", "restaurar"]);
});

test("esconde e depois restaura com o cofre", async () => {
  const no = new Veu();
  const mensagem = `Oi, sou a Maria Souza, meu CPF é ${CPF}`;
  const [[item]] = await no.execute.call(contexto([{ mensagem }], { operation: "esconder", texto: mensagem, operador: "token", opcoes: {} }));
  assert.equal(item.json.textoProtegido, "Oi, sou a [PESSOA_1], meu CPF é [CPF_1]");
  assert.deepEqual(item.json.encontrados, { PESSOA: 1, CPF: 1 });
  assert.equal(item.json.mensagem, mensagem); // o campo original continua (para o fluxo decidir)
  const resposta = "Olá [PESSOA_1], seu CPF [CPF_1] está regular.";
  const [[restaurado]] = await no.execute.call(contexto([{}], { operation: "restaurar", texto: resposta, cofre: item.json.cofre }));
  assert.equal(restaurado.json.textoRestaurado, `Olá Maria Souza, seu CPF ${CPF} está regular.`);
  const [[deTexto]] = await no.execute.call(contexto([{}], { operation: "restaurar", texto: resposta, cofre: JSON.stringify(item.json.cofre) }));
  assert.equal(deTexto.json.textoRestaurado, restaurado.json.textoRestaurado);
});

test("recusa tipos bloqueados e respeita continuar em caso de erro", async () => {
  const no = new Veu();
  const chave = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----";
  await assert.rejects(no.execute.call(contexto([{}], { operation: "esconder", texto: chave, operador: "token", opcoes: {} })), /CHAVE_PRIVADA/);
  const [[item]] = await no.execute.call(contexto([{}], { operation: "esconder", texto: chave, operador: "token", opcoes: {} }, { continuar: true }));
  assert.match(item.json.erro, /CHAVE_PRIVADA/);
});

test("máscara e nunca esconder", async () => {
  const no = new Veu();
  const texto = `CPF ${CPF}, contato@empresa.example`;
  const [[item]] = await no.execute.call(contexto([{}], { operation: "esconder", texto, operador: "mascara",
    opcoes: { ignorar: "contato@empresa.example", campo: "seguro" } }));
  assert.equal(item.json.seguro, "CPF ***.982.247-**, contato@empresa.example");
});
