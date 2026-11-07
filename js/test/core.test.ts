import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { Veu, Vault, analyze, anonymize, keyKind, maskValue, session, summarize } from "../src/index.ts";
import { hmacSha256, sha256, toHex } from "../src/sha256.ts";

const veu = new Veu();

// Pedaços montados na hora: nenhum scanner de segredos confunde o teste com uma chave real.
const key = (...parts: string[]) => parts.join("");
let seed = 7;
const chars = (count: number, alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") =>
  Array.from({ length: count }, () => alphabet[(seed = (seed * 1103515245 + 12345) % 2 ** 31) % alphabet.length]).join("");

test("anonimiza e restaura", () => {
  const result = anonymize("Cliente Maria Souza, CPF 529.982.247-25");
  assert.equal(result.text, "Cliente [PESSOA_1], CPF [CPF_1]");
  assert.equal(result.restore("Olá [PESSOA_1] ([CPF_1])"), "Olá Maria Souza (529.982.247-25)");
  assert.deepEqual(result.counts(), { PESSOA: 1, CPF: 1 });
});

test("restauração tolerante a marcadores reescritos pelo modelo", () => {
  const result = veu.anonymize("CPF 529.982.247-25");
  assert.equal(result.restore("[CPF 1], CPF_1 e [CPF_1"), "529.982.247-25, 529.982.247-25 e 529.982.247-25");
});

test("streaming: marcador cortado entre pedaços", () => {
  const s = session();
  s.anonymize("Maria Souza, CPF 529.982.247-25");
  const restorer = s.restorer();
  const output = ["Olá [PES", "SOA_1], seu CPF é [CP", "F_1", "]. Fim"].map((part) => restorer.feed(part)).join("") + restorer.flush();
  assert.equal(output, "Olá Maria Souza, seu CPF é 529.982.247-25. Fim");
});

test("restoreStream com iterador assíncrono", async () => {
  const s = veu.session();
  s.anonymize("CPF 529.982.247-25");
  async function* chunks() {
    yield "Seu [";
    yield "CPF_";
    yield "1] ok";
  }
  let text = "";
  for await (const part of s.restoreStream(chunks())) text += part;
  assert.equal(text, "Seu 529.982.247-25 ok");
});

test("sessão reutiliza o marcador e anonimiza objetos", () => {
  const s = veu.session();
  const messages = s.anonymizeData([{ role: "user", content: "CPF 529.982.247-25" }, { role: "user", content: "de novo 52998224725" }]);
  assert.equal(messages[0].content, "CPF [CPF_1]");
  assert.equal(messages[1].content, "de novo [CPF_1]");
  assert.deepEqual(s.counts(), { CPF: 2 });
});

test("nomes parciais usam o marcador do nome completo", () => {
  assert.equal(veu.anonymize("João da Silva ligou. Depois João mandou email.").text, "[PESSOA_1] ligou. Depois [PESSOA_1] mandou email.");
});

test("operador hash é igual ao do Python (HMAC-SHA256)", () => {
  const hashed = new Veu({ operator: "hash", secret: "segredo-de-teste" });
  // Chave derivada só para o operador hash, 64 bits na saída (mesmo valor do Python).
  const key = createHmac("sha256", "segredo-de-teste").update("veu/hash/v2").digest();
  const expected = createHmac("sha256", key).update("CPF:52998224725").digest("hex").slice(0, 16);
  assert.equal(expected, "25cf014c9ab44c77");
  assert.equal(hashed.anonymize("CPF 529.982.247-25").text, `CPF [CPF_${expected}]`);
  assert.equal(toHex(sha256(new TextEncoder().encode("abc"))), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  const long = "x".repeat(200);
  assert.equal(toHex(hmacSha256(new TextEncoder().encode(long), new TextEncoder().encode(long))),
    createHmac("sha256", long).update(long).digest("hex"));
});

test("máscara e remoção", () => {
  assert.equal(veu.withOperator("mascara").anonymize("CPF 529.982.247-25").text, "CPF ***.982.247-**");
  assert.equal(veu.withOperator("remover").anonymize("CPF 529.982.247-25").text, "CPF [CPF]");
  assert.throws(() => veu.withOperator("sintetico"), /ainda não está disponível/);
});

test("cofre exportado no formato do Python", () => {
  const result = veu.anonymize("CPF 529.982.247-25");
  const copy = Vault.fromJSON(JSON.parse(JSON.stringify(result.vault)));
  assert.equal(copy.restore("[CPF_1]"), "529.982.247-25");
  assert.equal(copy.placeholder("CPF", "111.444.777-35"), "[CPF_2]");
});

test("opções: tipos, exceções e padrões próprios", () => {
  assert.deepEqual(new Veu({ labels: ["CPF"] }).analyze("Maria Souza 529.982.247-25").map((e) => e.label), ["CPF"]);
  assert.equal(new Veu({ allowlist: ["contato@empresa.example"] }).anonymize("contato@empresa.example").text, "contato@empresa.example");
  assert.equal(new Veu({ allowPatterns: ["@empresa\\.example$"] }).anonymize("a@empresa.example").text, "a@empresa.example");
  const custom = new Veu({ customPatterns: [{ entidade: "MATRICULA", padrao: "MAT-\\d{6}" }] });
  assert.equal(custom.anonymize("matrícula MAT-123456").text, "matrícula [MATRICULA_1]");
  assert.deepEqual(new Veu({ detectors: ["padroes"] }).analyze("Maria Souza").map((e) => e.label), []);
});

test("segredos com prefixo conhecido", () => {
  const keys = [
    key("sk-", "proj-", chars(20), "T3Blbk", chars(20)),
    key("sk-", "ant-", "api03-", chars(93), "AA"),
    key("AI", "za", chars(35)),
    key("gh", "p_", chars(36)),
    key("sk", "_live_", chars(24)),
    key("nt", "n_", chars(46)),
  ];
  for (const secret of keys) {
    assert.deepEqual(analyze(`use ${secret} aqui`).map((e) => [e.label, e.text]), [["CHAVE_API", secret]]);
  }
});

test("segredos por nome de campo e prosa", () => {
  const value = chars(32);
  const found = analyze(`API_KEY=${value}\nDB_PASSWORD=hunter2!\na senha do wifi é Gato2024`).map((e) => [e.label, e.text]);
  assert.deepEqual(found, [["SEGREDO", value], ["SENHA", "hunter2!"], ["SENHA", "Gato2024"]]);
  for (const text of ["Senha: deve conter 8 caracteres", "password = getpass()", "max_tokens: 2048", "password: [SENHA_1]"]) {
    assert.deepEqual(analyze(text), [], text);
  }
  assert.equal(keyKind("clientSecret"), "SEGREDO");
  assert.equal(keyKind("token_url"), null);
});

test("chave privada e máscaras de segredos", () => {
  const pem = `-----BEGIN RSA PRIVATE KEY-----\n${chars(64)}\n-----END RSA PRIVATE KEY-----`;
  assert.deepEqual(analyze(pem).map((e) => e.label), ["CHAVE_PRIVADA"]);
  assert.equal(maskValue("CHAVE_API", key("sk-", "proj-", chars(30))), "sk-proj-****");
  assert.equal(maskValue("SENHA", "x"), "********");
  assert.deepEqual(summarize(`DB_PASSWORD=hunter2! e CPF 529.982.247-25`), { SENHA: 1, CPF: 1 });
});

test("cache de detecção: mesmo resultado, sem guardar texto, e desligável", () => {
  const longo = "Histórico do atendimento. A cliente Maria Souza, CPF 529.982.247-25, pediu a segunda via. ".repeat(4);
  const comCache = new Veu();
  const primeiro = comCache.analyze(longo);
  const segundo = comCache.analyze(longo);
  assert.deepEqual(segundo, primeiro);
  assert.equal(comCache.analyzer.cache!.hits, 1);
  assert.ok(!JSON.stringify([...(comCache.analyzer.cache as unknown as { items: Map<string, unknown> }).items]).includes("Maria"));
  assert.equal(new Veu({ cache: 0 }).analyzer.cache, null);
  comCache.analyze("CPF 529.982.247-25");
  assert.equal(comCache.analyzer.cache!.size, 1); // textos curtos não entram
});
