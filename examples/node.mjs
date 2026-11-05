// Node.js com o SDK oficial da OpenAI passando pelo proxy do Véu.
//   npm install openai
//   veu servir                      (em outro terminal)
//   OPENAI_API_KEY=... node examples/node.mjs
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "http://127.0.0.1:8787/v1" });

const resposta = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Sou a Maria Souza, CPF 529.982.247-25. Confirme meu cadastro." }],
});

// O modelo viu [PESSOA_1] e [CPF_1]; aqui chegam os dados reais.
console.log(resposta.choices[0].message.content);
