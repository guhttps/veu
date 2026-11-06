<p align="center">
  <img src="docs/banner.png" alt="Véu: esconde CPF, nomes, telefones e endereços antes de o texto chegar à IA e devolve os dados reais na resposta" width="100%">
</p>

<p align="center">
  <a href="https://github.com/guhttps/veu/actions/workflows/ci.yml"><img src="https://github.com/guhttps/veu/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%20a%203.14-3776AB" alt="Python 3.11 a 3.14">
  <img src="https://img.shields.io/badge/node-22%2B-5FA04E" alt="Node 22 ou mais novo">
  <img src="https://img.shields.io/badge/depend%C3%AAncias%20do%20n%C3%BAcleo-0-2ea44f" alt="Núcleo sem dependências">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/guhttps/veu" alt="Licença MIT"></a>
</p>

# Véu

**O Véu esconde dados pessoais e segredos antes de um texto chegar a um modelo de IA e devolve os dados reais na resposta.** A IA trabalha com `[PESSOA_1]`, `[CPF_1]` e `[CHAVE_API_1]`. Quem usa vê "Maria Souza", "529.982.247-25" e a chave de verdade.

Empresas estão colocando IA no atendimento, nos contratos, no RH e no código. Junto com cada pergunta vão CPF, nome e telefone de clientes, e também chaves de API, senhas e URLs de banco de dados. O Véu fica no meio do caminho:

- **Entende documentos brasileiros de verdade:** confere os dígitos verificadores, inclusive do **CNPJ alfanumérico** de 2026.
- **Reconhece segredos:** chaves de mais de 30 serviços, tokens, senhas e chaves privadas.
- **Funciona em streaming.**
- **Chega de vários jeitos:** página web, extensão de navegador, biblioteca Python ou JavaScript, proxy, gateway da empresa, plugin para agentes de código.

```text
Você envia     Sou a Maria Souza, CPF 529.982.247-25. Use a chave sk-proj-4f...
A IA recebe    Sou a [PESSOA_1], CPF [CPF_1]. Use a chave [CHAVE_API_1]
A IA responde  Olá, [PESSOA_1]! Configurei [CHAVE_API_1] no .env.
Você recebe    Olá, Maria Souza! Configurei sk-proj-4f... no .env.
```

> [!IMPORTANT]
> Nenhuma detecção automática é perfeita. O Véu **reduz** muito o risco de enviar dados pessoais, mas não o elimina. Veja os [números do benchmark](#benchmark) e as [limitações](SECURITY.md#o-que-o-véu-não-faz). Não é aconselhamento jurídico sobre a LGPD.

## Comece por aqui

| Você... | Use | Instalação |
|---|---|---|
| **usa ChatGPT, Claude ou Gemini no navegador** e não programa | A [**página do Véu**](https://guhttps.github.io/veu/): cole, copie a versão protegida, traga a resposta de volta. Tudo roda no seu navegador. | nenhuma |
| | A [**extensão**](docs/extensao.md) para Chrome e Edge, que protege o que você cola e digita nos sites das IAs | um clique |
| **programa em Python** | `openai_client()`, `anthropic_client()`, LangChain, `@protect`, MCP | `pip install "veu @ git+https://github.com/guhttps/veu"` |
| **programa em JavaScript ou TypeScript** | [`@guhttps/veu`](js/README.md): `createFetch()` para os SDKs da OpenAI e da Anthropic e middleware para o AI SDK da Vercel | `npm install @guhttps/veu` |
| **usa Claude Code ou Cursor** | O [**plugin**](docs/integracoes.md#claude-code-e-cursor): bloqueia segredos nos prompts e nos arquivos e lê Notion, planilhas e documentos já protegidos | `/plugin install veu --marketplace guhttps/veu` |
| **é da TI de uma empresa** | [**Gateway central**](docs/empresas.md) (Helm ou Docker), **guardrail para o LiteLLM** ou a **extensão gerenciada por política**. Nada é instalado nos computadores. | [guia para empresas](docs/empresas.md) |
| **quer dar Notion, planilhas ou PDFs para a IA** | `veu ler <link ou arquivo>` e `veu anonimizar planilha.xlsx` | [fontes e documentos](docs/integracoes.md#notion-google-e-documentos) |

Quer ver funcionando sem chave de API? Rode `veu demonstrar`: ele mostra, dado por dado, o que chegaria à IA com e sem o Véu.

## Recursos

- 🇧🇷 **28 tipos de dados:**
  - documentos brasileiros: CPF, CNPJ (numérico e alfanumérico), RG, CNH, título de eleitor, PIS/NIT, cartão do SUS e passaporte;
  - contatos e localização: nomes de pessoas, telefone (brasileiro e internacional), e-mail, endereço, CEP e IP;
  - financeiros: cartão, conta bancária, IBAN e chave Pix;
  - outros: placa, RENAVAM, data de nascimento e processo do CNJ;
  - **segredos**.
- 🔑 **Segredos:**
  - chaves da OpenAI, Anthropic, AWS, Google, GitHub, GitLab, Stripe, Slack, Hugging Face, Groq, Notion, Mercado Pago, Asaas e mais 20 serviços;
  - JWT e tokens Bearer;
  - senhas (`DB_PASSWORD=...`, "a senha é ...");
  - chaves privadas;
  - URLs de banco com senha;
  - campos como `api_key: ...`.
- ✅ **Validação de verdade:**
  - dígitos verificadores de CPF, CNPJ, PIS, CNS, CNH, título, RENAVAM, processo CNJ, IBAN e Luhn;
  - DDDs válidos.

  Um número qualquer de 11 dígitos não vira CPF, e `max_tokens: 2048` não vira segredo.
- 🧠 **Nomes sem modelo de IA:**
  - listas de nomes brasileiros, capitalização e contexto ("Sr.", "cliente", "oi joão");
  - não confunde "Banco do Brasil", "Rua Augusta" nem "São José dos Campos";
  - opcionalmente, spaCy ou um modelo local.
- 🔁 **Reversível e consistente:**
  - o mesmo dado recebe sempre o mesmo marcador;
  - "João" sozinho é ligado a "João da Silva";
  - a restauração tolera o que os modelos fazem com os marcadores (`[CPF 1]`, `CPF_1`).
- 🌊 **Streaming de verdade:**
  - marcadores partidos entre pedaços ("[PES" + "SOA_1]") são remontados;
  - vale também para argumentos de ferramentas.
- 📄 **Notion, Google e documentos:**
  - lê páginas e bases do Notion, Google Docs, Sheets e Slides, links e PDFs, já protegidos;
  - anonimiza Word, Excel e PowerPoint **no próprio formato**, mantendo a formatação e as fórmulas.
- 🌐 **Python, JavaScript e navegador:**
  - a mesma detecção nas três versões;
  - um teste de conformidade com 235 casos exige resultados idênticos.
- 🏢 **Pronto para empresas:**
  - gateway central com tokens por equipe e auditoria encadeada à prova de adulteração;
  - sessões no Redis para várias réplicas;
  - desvio de dados sensíveis para um modelo interno;
  - chart Helm, guardrail para o LiteLLM e extensão com política gerenciada.
- 🤖 **Agentes:**
  - servidor MCP, ganchos para Claude Code e Cursor e plugin com skill;
  - o agente consegue trabalhar com arquivos sensíveis sem ver os dados.
- 🎭 **5 operadores:** marcador, valor sintético (outro CPF válido), máscara, remoção e hash estável.
- 🪶 **Leve:** o núcleo não tem dependências e processa cerca de 330 mil caracteres por segundo.

## Como funciona

```mermaid
flowchart LR
    A["Você ou sua aplicação<br/>(navegador, SDK, agente, n8n)"] -->|texto com dados reais| V
    subgraph V["Véu"]
        D["Detectores<br/>documentos · nomes · endereços · segredos"] --> C["Cofre<br/>[CPF_1] ↔ 529.982.247-25"]
    end
    V -->|só marcadores| L["Modelo de IA<br/>OpenAI · Anthropic · Gemini · Ollama"]
    L -->|resposta com marcadores| V
    V -->|resposta com os dados reais| A
```

O cofre com o mapeamento entre marcadores e dados reais fica só com você (na memória, no navegador ou no seu servidor) e nunca é enviado ao modelo. Uma instrução curta avisa o modelo para repetir os marcadores sem tentar adivinhar os valores.

## Instalação

```bash
pip install "veu[servidor] @ git+https://github.com/guhttps/veu"
```

- **Biblioteca Python sem dependências:**

  ```bash
  pip install "veu @ git+https://github.com/guhttps/veu"
  ```

- **Extras opcionais:**
  - `mcp`: servidor para agentes;
  - `documentos`: Word, Excel, PowerPoint e PDF;
  - `langchain` e `pandas`;
  - `litellm`: guardrail;
  - `redis`: sessões compartilhadas;
  - `spacy`;
  - `todos`, que instala os anteriores.

  Exemplo:

  ```bash
  pip install "veu[servidor,mcp,documentos] @ git+https://github.com/guhttps/veu"
  ```

- **JavaScript e TypeScript:** `npm install @guhttps/veu`. Veja o [js/README.md](js/README.md).
- **Navegador:** a [página](https://guhttps.github.io/veu/) ou a [extensão](docs/extensao.md).
- **Docker:**

  ```bash
  docker run -p 8787:8787 -e VEU_TOKEN=um-segredo ghcr.io/guhttps/veu
  ```

  O token é obrigatório fora do localhost. Para a empresa toda, veja o [guia para empresas](docs/empresas.md).

## Uso rápido

### 1. Como proxy (qualquer linguagem, muda uma linha)

```bash
veu servir            # http://127.0.0.1:8787, com playground em /veu/playground
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1")            # OpenAI
groq = OpenAI(base_url="http://127.0.0.1:8787/groq/v1")         # Groq, OpenRouter, Ollama, Maritaca...
```

### 2. Dentro do seu código, sem proxy

```python
from veu.integrations.sdk import openai_client, anthropic_client

client = openai_client()         # igual a openai.OpenAI(...), mas protegido pelo Véu
```

```ts
import OpenAI from "openai";
import { createFetch } from "@guhttps/veu/fetch";

const client = new OpenAI({ fetch: createFetch() });   // o mesmo para a Anthropic
```

### 3. Como biblioteca

```python
import veu

resultado = veu.anonymize("Oi, sou o João da Silva, CPF 529.982.247-25, tel (11) 91234-5678.")
resultado.text
# 'Oi, sou o [PESSOA_1], CPF [CPF_1], tel [TELEFONE_1].'
veu.restore("Certo, [PESSOA_1]. Vou ligar no [TELEFONE_1].", resultado.vault)
# 'Certo, João da Silva. Vou ligar no (11) 91234-5678.'
```

### 4. Notion, planilhas e documentos

```bash
veu ler https://www.notion.so/minha-empresa/Atendimento-1f2e...   # NOTION_TOKEN no ambiente
veu ler https://docs.google.com/spreadsheets/d/.../edit           # público pelo link ou GOOGLE_ACCESS_TOKEN
veu anonimizar clientes.xlsx -o clientes-protegido.xlsx --cofre cofre.json
veu restaurar resposta.docx --cofre cofre.json -o resposta-final.docx
```

## Integrações

| Categoria | Integrações | Guia |
|---|---|---|
| **No navegador** | Página que roda localmente; extensão para ChatGPT, Claude, Gemini, Copilot, Perplexity, DeepSeek, Mistral, Grok e outros | [Extensão](docs/extensao.md) |
| **Modelos de IA** (proxy) | OpenAI, Anthropic, Gemini, Ollama nativo, Azure OpenAI e 20 provedores prontos (Groq, OpenRouter, DeepSeek, Mistral, xAI, Maritaca, vLLM...) | [Modelos](docs/integracoes.md#modelos-de-ia) |
| **Python** | `openai_client()`, `anthropic_client()`, transportes `httpx`, LangChain, `@protect`, `veu.session()` | [SDKs](docs/integracoes.md#atalhos-dos-sdks) |
| **JavaScript** | `createFetch()` para os SDKs da OpenAI e da Anthropic, middleware do AI SDK da Vercel, uso no navegador | [@guhttps/veu](js/README.md) |
| **Agentes** | Servidor MCP (`ler_protegido`, `anonimizar_arquivo`...), ganchos e plugin com skill para Claude Code, ganchos para Cursor | [Agentes](docs/integracoes.md#claude-code-e-cursor) |
| **Fontes** | Notion (páginas e bases), Google Docs/Sheets/Slides, links; Word, Excel, PowerPoint e PDF | [Fontes](docs/integracoes.md#notion-google-e-documentos) |
| **Empresas** | Gateway com equipes, auditoria encadeada, Redis, desvio para modelo interno; guardrail do LiteLLM; Helm e docker-compose | [Empresas](docs/empresas.md) |
| **Dados** | CSV, JSON, JSONL, Excel, pandas e RAG, com o mesmo marcador em todas as linhas | [Dados](docs/integracoes.md#dados) |
| **Observabilidade** | `logging`, structlog, loguru, Sentry e Prometheus | [Observabilidade](docs/integracoes.md#observabilidade) |
| **Repositórios** | Pre-commit e GitHub Action com SARIF (agora também acham chaves e senhas) | [Repositórios](docs/integracoes.md#repositórios) |

## O que é detectado

| Tipo | Exemplo | Como |
|---|---|---|
| `PESSOA` | Maria Aparecida da Silva, "oi joão" | listas de nomes, capitalização e contexto |
| `CPF` | 529.982.247-25 | formato + dígitos verificadores |
| `CNPJ` | 11.222.333/0001-81, 12.ABC.345/01DE-35 | numérico e alfanumérico + dígitos |
| `TELEFONE` | (11) 91234-5678, +44 20 7946 0958 | DDD válido; internacional com + |
| `EMAIL`, `ENDERECO`, `CEP`, `IP` | Rua das Flores, 123, apto 45 | formato e contexto |
| `RG`, `CNH`, `TITULO_ELEITOR`, `PIS`, `CNS`, `RENAVAM`, `PASSAPORTE` | — | contexto e dígitos verificadores |
| `PLACA` | ABC-1234, BRA2E19 | padrão antigo e Mercosul |
| `CARTAO_CREDITO`, `CONTA_BANCARIA`, `CHAVE_PIX`, `IBAN` | DE89 3704 0044 0532 0130 00 | Luhn, módulo 97 e contexto |
| `DATA_NASCIMENTO`, `PROCESSO` | nascida em 12/03/1990 | contexto e dígitos do CNJ |
| `CHAVE_API` | `sk-proj-...`, `AKIA...`, `ghp_...`, `APP_USR-...` | prefixos de mais de 30 serviços |
| `TOKEN` | `eyJhbGci...`, `Bearer ...` | JWT, Bearer e Basic |
| `SENHA`, `SEGREDO` | `DB_PASSWORD=...`, `clientSecret: ...` | nome do campo + cara de valor aleatório |
| `CHAVE_PRIVADA`, `URL_CONEXAO` | `-----BEGIN PRIVATE KEY-----`, `postgres://u:senha@host` | formato |

Também dá para adicionar padrões próprios (matrícula, número de cliente...) no [`veu.toml`](examples/veu.toml).

## Operadores

| Operador | Resultado | Reversível |
|---|---|---|
| `token` (padrão) | `[CPF_1]` | sim |
| `sintetico` | `686.192.633-74` (outro CPF válido), outro nome, chave falsa no mesmo formato | sim |
| `mascara` | `***.982.247-**`, `sk-proj-****` | não |
| `remover` | `[CPF]` | não |
| `hash` | `[CPF_3fa2c1d9]`, estável entre requisições com o mesmo `VEU_SEGREDO` | sim, com o cofre |

O operador `sintetico` ainda só existe em Python. Em JavaScript, use `token`, `mascara`, `remover` ou `hash`.

## Benchmark

O Véu vem com um gerador de textos realistas (atendimento, saúde, jurídico, RH, conversas de WhatsApp, formulários) com dados **falsos** e anotados, e um conjunto de casos difíceis escritos à mão. A métrica principal é o **vazamento**: a fração dos dados pessoais que chegaria ao modelo sem estar totalmente escondida.

```bash
veu avaliar --quantidade 1000
```

| Conjunto | Textos | Precisão | Revocação | Vazamento geral | Vazamento de nomes |
|---|---:|---:|---:|---:|---:|
| Validação (modelos de texto **não usados** para ajustar o detector) | 1.000 | 100,0% | 97,5% | **2,5%** | 6,5% |
| Validação, com o detector spaCy ligado | 1.000 | 97,8% | 98,6% | **1,2%** | 3,0% |
| Casos difíceis escritos à mão | 25 | 100,0% | 100,0% | 0,0% | 0,0% |
| Desenvolvimento (modelos usados no ajuste) | 1.000 | 100,0% | 100,0% | 0,0% | 0,0% |

Como ler esses números com honestidade:

- **O número que importa é o da validação.** O conjunto de desenvolvimento chega a 100% porque o detector foi ajustado olhando para ele.
- **Documentos com dígitos verificadores** (CPF, CNPJ, cartão, processo...) ficaram em 0% de vazamento nos três conjuntos.
- **Nomes são a parte difícil**, principalmente em minúsculas, em conversas sem saudação ("kkkk o rayane esqueceu").
- **O detector de segredos não mudou a precisão:** com ele ligado, os números da validação são os mesmos.
- **O spaCy reduz o vazamento de nomes para menos da metade, mas é cerca de 18 vezes mais lento.**
- **Os textos são sintéticos.** Em dados reais, espere resultados piores. Teste com uma amostra dos seus próprios textos antes de confiar.

Detalhes da metodologia em [docs/benchmark.md](docs/benchmark.md).

## Configuração

Tudo funciona sem configuração. Para ajustar, crie um `veu.toml` (exemplo completo em [examples/veu.toml](examples/veu.toml)):

```toml
[deteccao]
limiar = 0.5                                   # 0 a 1; mais alto = menos falsos positivos
ignorar = ["contato@minhaempresa.example"]      # valores que nunca são escondidos

[anonimizacao]
operador = "token"

[politica]
bloquear = ["CARTAO_CREDITO", "CHAVE_PRIVADA"] # recusa a requisição em vez de só esconder

[servidor]
log_auditoria = "veu-auditoria.jsonl"          # só contagens, nunca os valores, em cadeia de hashes
```

Equipes, sessões no Redis, desvio para modelo interno e expansão de links do Notion estão no [guia para empresas](docs/empresas.md).

## Segurança

- **Acesso:**
  - o Véu ouve só em `127.0.0.1` por padrão e recusa requisições de outros sites (CSRF e DNS rebinding);
  - fora do localhost, ele **não inicia sem token**;
  - cada equipe pode ter o seu token e a sua política.
- **Dados:**
  - o cofre fica na memória (ou no seu Redis) e expira sem uso;
  - sessões de credenciais diferentes nunca compartilham o cofre;
  - a página e a extensão não enviam nada pela internet.
- **Auditoria:** o log tem só contagens, em cadeia de hashes (HMAC com segredo). `veu auditoria verificar` aponta linhas alteradas ou removidas.
- **Limites:** o Véu protege os dados do provedor de IA, mas não decide quem pode ver o quê dentro da sua aplicação. Veja as [limitações](SECURITY.md#o-que-o-véu-não-faz).

Leia o [modelo de ameaças e as limitações](SECURITY.md) antes de usar em produção.

## Desenvolvimento

```bash
git clone https://github.com/guhttps/veu && cd veu
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # 282 testes, inclusive com os SDKs oficiais, LangChain, MCP, Office e Redis
ruff check .
veu avaliar               # benchmark
cd js && npm ci && npm test                       # biblioteca JavaScript (inclui a conformidade com o Python)
node extensao/teste/e2e.mjs                        # extensão e página num Chrome de verdade
```

Veja o [guia de contribuição](CONTRIBUTING.md). Contribuições de nomes, padrões de documentos, formatos de chaves e casos difíceis são muito bem-vindas.

## Próximos passos

- [ ] Publicar no PyPI (`pip install veu`), no npm (`@guhttps/veu`) e na Chrome Web Store
- [ ] Operador sintético na versão JavaScript
- [ ] Mais casos difíceis escritos à mão, de domínios reais (com dados fictícios)
- [ ] Detector de nomes em minúsculas sem saudação ("o rayane esqueceu")
- [ ] Biblioteca para Go e Java
- [ ] Suporte à API Realtime e a uploads de arquivos

## Licença

[MIT](LICENSE). Os dados usados nos exemplos e no benchmark são fictícios.
