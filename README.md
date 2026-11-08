<p align="center">
  <img src="docs/banner.png" alt="Véu: esconde dados pessoais e segredos antes de o texto chegar à IA e devolve os dados reais na resposta" width="100%">
</p>

<p align="center">
  <a href="https://github.com/guhttps/veu/actions/workflows/ci.yml"><img src="https://github.com/guhttps/veu/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/veu/"><img src="https://img.shields.io/pypi/v/veu" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/@guhttps/veu"><img src="https://img.shields.io/npm/v/@guhttps/veu" alt="npm"></a>
  <img src="https://img.shields.io/badge/python-3.11%20a%203.14-3776AB" alt="Python 3.11 a 3.14">
  <img src="https://img.shields.io/badge/depend%C3%AAncias%20do%20n%C3%BAcleo-0-2ea44f" alt="Núcleo sem dependências">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/guhttps/veu" alt="Licença MIT"></a>
</p>

# Véu

**O Véu esconde dados pessoais e segredos antes de um texto chegar a uma IA e devolve os dados reais na resposta.** A IA trabalha com `[PESSOA_1]`, `[EMAIL_1]` e `[CHAVE_API_1]`. Você vê os dados de verdade.

```text
Você envia     Sou a Maria Souza (maria@example.com), CPF 529.982.247-25. Use a chave sk-proj-4f9a...
A IA recebe    Sou a [PESSOA_1] ([EMAIL_1]), CPF [CPF_1]. Use a chave [CHAVE_API_1]
A IA responde  Pronto, [PESSOA_1]! Configurei [CHAVE_API_1] no seu .env.
Você recebe    Pronto, Maria Souza! Configurei sk-proj-4f9a... no seu .env.
```

Empresas e pessoas estão colocando IA no atendimento, nos contratos, no RH e no código. Junto com cada pergunta vão nomes, documentos e contatos de clientes, e também chaves de API e senhas. O Véu fica no meio do caminho e protege:

- **Dados pessoais de qualquer país:** nomes, e-mails, telefones (com código de qualquer país), cartões, IBAN, endereços IP e datas de nascimento.
- **Documentos brasileiros, conferidos de verdade:** CPF, CNPJ (inclusive o alfanumérico de 2026), RG, CNH, PIS, cartão do SUS e outros, pelos dígitos verificadores.
- **Segredos de qualquer serviço:** chaves de API de mais de 30 serviços, tokens, senhas, chaves privadas e URLs de banco com senha.

E funciona do jeito que você usa IA: no navegador, no computador, no seu código ou no servidor da empresa.

> [!NOTE]
> O Véu nasceu no Brasil: os documentos brasileiros têm o suporte mais completo e a interface está em português. E-mails, telefones internacionais, cartões, IBAN, IPs e segredos funcionam em textos de qualquer lugar. Documentos de Portugal e de nove países da América Latina também são reconhecidos, com dígito verificador. Os nomes são reconhecidos pelas listas do Censo 2022; para nomes de outras línguas, ligue o detector spaCy ou um modelo local.

> [!IMPORTANT]
> Nenhuma detecção automática é perfeita. O Véu **reduz** muito o risco de enviar dados pessoais, mas não o elimina. Veja os [números do benchmark](#benchmark) e as [limitações](SECURITY.md#o-que-o-véu-não-faz). Não é aconselhamento jurídico sobre a LGPD.

## Comece por aqui

| Você quer... | Use | Como |
|---|---|---|
| **colar textos no ChatGPT, no Claude ou no Gemini** sem expor dados | A [**página do Véu**](https://guhttps.github.io/veu/): cole, copie a versão protegida, traga a resposta de volta | Nada para instalar |
| **proteger planilhas, documentos e PDFs** ou conectar o **Claude Desktop**, sem programar | O [**painel do Véu**](#instalar-sem-saber-programar), no seu computador | [Um comando, 2 minutos](#instalar-sem-saber-programar) |
| **proteger aplicativos como n8n, Make e Zapier** | O painel mostra o endereço para colar no aplicativo | [Um comando, 2 minutos](#instalar-sem-saber-programar) |
| **programar em Python** | `openai_client()`, `anthropic_client()`, LangChain, `@protect` | `pip install veu` |
| **programar em JavaScript ou TypeScript** | [`@guhttps/veu`](js/README.md), com `createFetch()` e middleware do AI SDK | `npm install @guhttps/veu` |
| **proteger o Claude Code ou o Cursor** | O [**plugin**](docs/integracoes.md#claude-code-e-cursor): bloqueia segredos em prompts e arquivos | `/plugin install veu --marketplace guhttps/veu` |
| **proteger a empresa toda** sem instalar nada nos computadores | [**Gateway central**](docs/empresas.md), **guardrail do LiteLLM** ou **extensão gerenciada** | [Guia para empresas](docs/empresas.md) |

Quer ver funcionando antes? Depois de instalar, rode `veu demonstrar`. Ele mostra, dado por dado, o que chegaria à IA com e sem o Véu e o que acontece quando a IA é manipulada para mandar os dados para fora, sem precisar de chave de API. Em CI, ele sai com erro se algo vazar.

## Instalar sem saber programar

**No Windows:** aperte a tecla Windows, digite **PowerShell**, aperte Enter e cole:

```powershell
irm https://guhttps.github.io/veu/instalar.ps1 | iex
```

**No Mac ou no Linux:** abra o **Terminal** e cole:

```bash
curl -LsSf https://guhttps.github.io/veu/instalar.sh | sh
```

Em cerca de dois minutos o instalador:

- **prepara tudo:** instala o Python e o Véu na sua pasta de usuário, sem pedir administrador;
- **cria o atalho:** o atalho **Véu** fica na área de trabalho;
- **abre o painel:** o painel aparece no navegador.

O passo a passo com imagens está em [guhttps.github.io/veu/instalar.html](https://guhttps.github.io/veu/instalar.html).

<p align="center"><img src="docs/painel.png" alt="Painel do Véu: proteger um arquivo, proteger um texto e conectar aplicativos" width="90%"></p>

No painel, tudo é feito com cliques:

- **Proteger um arquivo:**
  - arraste uma planilha, um documento, uma apresentação ou um PDF e baixe a versão protegida, no mesmo formato;
  - quando a IA devolver um arquivo, **Colocar os dados de volta** restaura os dados reais.
- **Proteger um texto:** cole, copie a versão protegida e cole a resposta da IA para ver os dados reais.
- **Usar com aplicativos:**
  - conecte o **Claude Desktop** ou o **Cursor** com um botão;
  - copie o endereço para n8n, Make, Zapier e outros apps.
- **O que proteger:**
  - caixinhas para nomes, documentos (do Brasil e de outros países), dados financeiros, senhas e outros;
  - usar um modelo no seu computador (Ollama) quando o texto tiver dados pessoais, para eles nem saírem da máquina;
  - uma lista de dados da empresa que nunca devem ser escondidos;
  - a opção de ligar o Véu junto com o computador.
- **Atividade:** quantos dados foram protegidos e os pedidos recentes, com o destino e quantos dados foram escondidos e voltaram (só contagens, nunca os valores).

Para abrir de novo, use o atalho **Véu** ou rode `veu painel`.

## Recursos

- 🌍 **Dados pessoais de qualquer lugar:** nomes, e-mails, telefones (brasileiros e de qualquer país, com +código), endereços, cartões de crédito, IBAN, endereços IP (v4 e v6) e datas de nascimento.
- 🇧🇷 **Documentos brasileiros:** CPF, CNPJ (numérico e alfanumérico), RG, CNH, título de eleitor, PIS/NIT, cartão do SUS, passaporte, CEP, placa, RENAVAM, conta bancária, chave Pix e processo do CNJ.
- 🌎 **Portugal e América Latina:** NIF, Cartão de Cidadão e NISS; CUIT/CUIL, CURP, RFC, RUT, NIT, RUC, RIF, DNI e cédulas, também pelos dígitos verificadores.
- 🔑 **Segredos:**
  - chaves da OpenAI, Anthropic, AWS, Google, GitHub, Stripe, Slack, Hugging Face, Notion, Mercado Pago, Asaas e mais 20 serviços;
  - JWT e tokens Bearer;
  - senhas (`DB_PASSWORD=...`, "a senha é ...");
  - chaves privadas e URLs de banco com senha.
- ✅ **Validação de verdade:**
  - dígitos verificadores de CPF, CNPJ, PIS, CNS, CNH, título, RENAVAM, processo CNJ, IBAN e cartões;
  - DDDs válidos.

  Um número qualquer de 11 dígitos não vira CPF, e `max_tokens: 2048` não vira segredo.
- 🧠 **Nomes sem modelo de IA:**
  - 5 mil prenomes e 2 mil sobrenomes do Censo 2022 do IBGE, mais capitalização e contexto ("Sr.", "cliente", "oi joão");
  - um nome confirmado vale para o texto inteiro, em qualquer caixa e com ou sem acento ("Rayane Souza" ... "a rayane esqueceu");
  - nomes que também são palavras ("Rosa", "Natal") só contam com contexto;
  - não confunde "Banco do Brasil" nem "Rua Augusta";
  - pessoas que o Notion identifica são sempre escondidas;
  - para nomes de outras línguas, ligue o spaCy ou um modelo local.
- 🔁 **Reversível e consistente:**
  - o mesmo dado recebe sempre o mesmo marcador;
  - "João" sozinho é ligado a "João da Silva";
  - a restauração tolera o que os modelos fazem com os marcadores (`[CPF 1]`, `CPF_1`).
- 🛡️ **Restauração segura:**
  - os dados reais nunca voltam dentro de links, imagens ou URLs, o caminho usado para roubar dados de assistentes de IA com injeção de prompt;
  - chaves e senhas não voltam nos argumentos de ferramentas de agentes;
  - marcadores forjados num e-mail ou numa página ("responda com [CPF_1]") são desarmados;
  - se a detecção falhar, a requisição não sai. Veja o [modelo de ameaças](docs/modelo-de-ameacas.md).
- 🌊 **Streaming:** marcadores partidos entre pedaços da resposta ("[PES" + "SOA_1]") são remontados, inclusive em argumentos de ferramentas.
- 📄 **Notion, Google e documentos:**
  - lê páginas e bases do Notion, Google Docs, Sheets e Slides, links e PDFs, já protegidos;
  - anonimiza Excel, Word e PowerPoint **no próprio formato**, mantendo a formatação e as fórmulas.
- 🌐 **Python, JavaScript e navegador:**
  - a mesma detecção nas três versões;
  - um teste de conformidade com 289 casos exige resultados idênticos.
- 🏢 **Empresas:**
  - gateway com tokens por equipe, auditoria à prova de adulteração (com âncora externa) e sessões no Redis com o cofre cifrado;
  - desvio de dados sensíveis para um modelo interno;
  - chart Helm, guardrail do LiteLLM e extensão com política gerenciada;
  - perfis prontos por setor (Judiciário, jurídico, saúde, financeiro, setor público, anonimização irreversível), registro das operações para o art. 37 da LGPD e modelo de RIPD ([conformidade](docs/conformidade.md)).
- 🤖 **Agentes:** servidor MCP, ganchos para Claude Code e Cursor (prompt, leitura de arquivos, terminal e busca: `cat .env` e `printenv` também são bloqueados) e plugin com skill. Claude Code e Codex CLI podem rodar pelo proxy, com patches e comandos restaurados.
- 🪶 **Leve:** o núcleo não tem dependências e processa cerca de 330 mil caracteres por segundo. Agentes que reenviam a conversa inteira a cada turno não pagam de novo pelas mensagens antigas: um cache em memória guarda só as posições dos dados, nunca o texto.

## Como funciona

```mermaid
flowchart LR
    A["Você ou seu aplicativo<br/>(navegador, painel, SDK, agente, n8n)"] -->|texto com dados reais| V
    subgraph V["Véu"]
        D["Detectores<br/>documentos · nomes · endereços · segredos"] --> C["Cofre<br/>[CPF_1] ↔ 529.982.247-25"]
    end
    V -->|só marcadores| L["IA<br/>OpenAI · Anthropic · Gemini · Ollama"]
    L -->|resposta com marcadores| V
    V -->|resposta com os dados reais| A
```

O cofre com o mapeamento entre marcadores e dados reais fica só com você (no navegador, no seu computador ou no seu servidor) e nunca vai para a IA. Uma instrução curta avisa o modelo para repetir os marcadores sem tentar adivinhar os valores.

## Para programadores

### Instalação

```bash
pip install veu                              # biblioteca, sem dependências
pip install "veu[servidor,mcp,documentos]"   # com o proxy, o painel, o MCP e Excel/Word/PDF
npm install @guhttps/veu                     # JavaScript e TypeScript
docker run -p 8787:8787 -e VEU_TOKEN=um-segredo ghcr.io/guhttps/veu
```

Extras opcionais do pacote Python:

| Extra | Para |
|---|---|
| `servidor` | Proxy, painel e API REST |
| `mcp` | Servidor MCP para agentes |
| `documentos` | Excel, Word, PowerPoint e PDF |
| `langchain`, `pandas` | Integrações com essas bibliotecas |
| `litellm` | Guardrail do LiteLLM |
| `redis` | Sessões compartilhadas entre réplicas, com o cofre cifrado |
| `spacy` | Detector de nomes do spaCy |
| `todos` | Tudo acima, menos `litellm` e `spacy` |

### Como proxy (qualquer linguagem, muda uma linha)

```bash
veu servir            # http://127.0.0.1:8787
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1")            # OpenAI
groq = OpenAI(base_url="http://127.0.0.1:8787/groq/v1")         # Groq, OpenRouter, Ollama, Maritaca...
```

### Dentro do seu código, sem proxy

```python
from veu.integrations.sdk import openai_client, anthropic_client

client = openai_client()         # igual a openai.OpenAI(...), mas protegido pelo Véu
```

```ts
import OpenAI from "openai";
import { createFetch } from "@guhttps/veu/fetch";

const client = new OpenAI({ fetch: createFetch() });   // o mesmo para a Anthropic
```

### Como biblioteca

```python
import veu

resultado = veu.anonymize("Oi, sou o João da Silva, CPF 529.982.247-25, tel (11) 91234-5678.")
resultado.text
# 'Oi, sou o [PESSOA_1], CPF [CPF_1], tel [TELEFONE_1].'
veu.restore("Certo, [PESSOA_1]. Vou ligar no [TELEFONE_1].", resultado.vault)
# 'Certo, João da Silva. Vou ligar no (11) 91234-5678.'
```

### Notion, planilhas e documentos

```bash
veu ler https://app.notion.com/p/Atendimento-1f2e...             # NOTION_TOKEN no ambiente
veu ler https://docs.google.com/spreadsheets/d/.../edit           # público pelo link ou GOOGLE_ACCESS_TOKEN
veu anonimizar clientes.xlsx -o clientes-protegido.xlsx --cofre cofre.json
veu restaurar resposta.docx --cofre cofre.json -o resposta-final.docx
```

### Comandos

| Comando | O que faz |
|---|---|
| `veu painel` | Liga o Véu e abre o painel no navegador |
| `veu perfis` | Perfis prontos por setor; use com `--perfil` |
| `veu demonstrar` | Mostra o que chegaria à IA com e sem o Véu e testa ataques à restauração, sem chave de API |
| `veu ler <link ou arquivo>` | Lê Notion, Google, links e documentos já protegidos |
| `veu anonimizar` / `veu restaurar` | Protege e restaura textos, CSV, JSON, Excel, Word, PowerPoint e PDF |
| `veu detectar` | Lista os dados encontrados num texto |
| `veu verificar` | Falha se algum arquivo tiver dados pessoais ou segredos (pre-commit e CI) |
| `veu servir` | Proxy para as APIs de IA, com playground e API REST |
| `veu mcp` | Servidor MCP para Claude Desktop, Claude Code e Cursor |
| `veu gancho prompt` / `veu gancho arquivo` | Ganchos para Claude Code e Cursor |
| `veu auditoria verificar` | Confere a integridade do log de auditoria |
| `veu atalhos` | Cria o atalho Véu na área de trabalho |
| `veu avaliar` | Roda o benchmark (`--externo todos` para os conjuntos públicos de terceiros) |

## Integrações

| Categoria | Integrações | Guia |
|---|---|---|
| **Sem programar** | Página que roda no navegador, painel no computador, extensão (Chrome, Edge e Firefox) para ChatGPT, Claude, Gemini, Copilot, Perplexity e outros | [Instalar](#instalar-sem-saber-programar) · [Extensão](docs/extensao.md) |
| **Modelos de IA** (proxy) | OpenAI, Anthropic, Gemini, Ollama, Azure OpenAI e 20 provedores prontos (Groq, OpenRouter, DeepSeek, Mistral, xAI, Maritaca, vLLM...) | [Modelos](docs/integracoes.md#modelos-de-ia) |
| **Python** | `openai_client()`, `anthropic_client()`, transportes `httpx`, LangChain, `@protect`, `veu.session()` | [Python](docs/integracoes.md#python) |
| **JavaScript** | `createFetch()` para os SDKs da OpenAI e da Anthropic, middleware do AI SDK da Vercel, uso no navegador | [@guhttps/veu](js/README.md) |
| **Agentes** | Servidor MCP (`ler_protegido`, `anonimizar_arquivo`...), plugin e ganchos para Claude Code, ganchos para Cursor | [Agentes](docs/integracoes.md#claude-code-e-cursor) |
| **n8n** | Nó "Véu" (esconder e restaurar) e modelo de atendimento por WhatsApp com a Evolution API | [n8n](n8n/README.md) |
| **Open WebUI** | Filtro que esconde os dados das mensagens e devolve os dados reais nas respostas (beta) | [Open WebUI](docs/integracoes.md#open-webui) |
| **Fontes** | Notion (páginas e bases), Google Docs, Sheets e Slides, links, Excel, Word, PowerPoint e PDF | [Fontes](docs/integracoes.md#notion-google-e-documentos) |
| **Empresas** | Gateway com equipes, auditoria encadeada, Redis e desvio para modelo interno; guardrail do LiteLLM; Helm e docker-compose | [Empresas](docs/empresas.md) |
| **Dados** | CSV, JSON, JSONL, Excel, pandas e RAG, com o mesmo marcador em todas as linhas | [Dados](docs/integracoes.md#dados) |
| **Observabilidade** | `logging`, structlog, loguru, Sentry e Prometheus | [Observabilidade](docs/integracoes.md#observabilidade) |
| **Repositórios** | Pre-commit e GitHub Action com SARIF, que também acham chaves e senhas | [Repositórios](docs/integracoes.md#repositórios) |

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
| `NIF_PT`, `CC_PT`, `NISS_PT` | NIF 123 456 789, Cartão de Cidadão 12345678 9 ZZ1 | Portugal: dígitos verificadores e contexto |
| `CUIT`, `DNI`, `CURP`, `RFC`, `RUT`, `CEDULA`, `NIT`, `RUC`, `RIF` | 20-12345678-6, XAXX900101HDFXXX03, 12.345.678-5 | Argentina, México, Chile, Uruguai, Colômbia, Peru, Equador, Paraguai e Venezuela: dígitos verificadores e contexto |

Formatos estruturados (CURP, RFC, Cartão de Cidadão, CUIT e RIF com a pontuação típica) são reconhecidos sozinhos. Números puros, que um CPF ou um protocolo poderiam imitar, só com a palavra de contexto por perto ("NIF", "CUIT", "RUC", "cédula"). Num formato que existe nos dois lados, como `12.345.678-5`, sem contexto, vence o rótulo brasileiro.

Também dá para adicionar padrões próprios (matrícula, número de cliente...) no [`veu.toml`](examples/veu.toml).

## Operadores

| Operador | Resultado | Reversível |
|---|---|---|
| `token` (padrão) | `[CPF_1]` | sim |
| `sintetico` | `686.192.633-74` (outro CPF válido), outro nome, chave falsa no mesmo formato | sim |
| `mascara` | `***.982.247-**`, `sk-proj-****` | não |
| `remover` | `[CPF]` | não |
| `hash` | `[CPF_3fa2c1d9e07b4a12]`, estável entre requisições com o mesmo `VEU_SEGREDO` (mínimo de 32 caracteres) | sim, com o cofre |

O operador `sintetico` ainda só existe em Python. Em JavaScript, use `token`, `mascara`, `remover` ou `hash`.

## Benchmark

A métrica principal é o **vazamento**: a fração dos dados pessoais que chegaria à IA sem estar totalmente escondida. O Véu é medido com conjuntos próprios e com **dois conjuntos públicos escritos por outras equipes**, e comparado com o Microsoft Presidio nos mesmos textos.

```bash
veu avaliar                    # conjuntos próprios
veu avaliar --externo todos    # BR-Agentic e privacy-filter-br (baixados uma vez, versão fixa)
```

| Conjunto | Véu | Véu + spaCy | Presidio |
|---|---:|---:|---:|
| Desafio: 41 textos escritos à mão e congelados | **22,0%** | 14,0% | 50,0% |
| [BR-Agentic](https://huggingface.co/datasets/guardion/BR-Agentic-PII-Benchmark): conversas bancárias com ferramentas | **22,2%** | 16,9% | 53,1% |
| [privacy-filter-br](https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset): 3.000 documentos | **0,4%** | 0,3% | 52,0% |
| Validação própria: 1.000 textos de modelos não usados no ajuste | **2,5%** | 1,2% | — |

Como ler esses números com honestidade:

- **Os conjuntos externos são o número que importa.** O ajuste dos detectores nunca olha para eles nem para o desafio. Os números próprios são melhores porque o gerador e o detector foram escritos pela mesma pessoa.
- **Documentos brasileiros são a maior vantagem:** o Presidio não tem reconhecedores de CPF, CNPJ, RG ou endereços brasileiros e vaza 90% dos CPFs; o Véu, menos de 1%.
- **Nomes são a parte difícil.** Com as listas do Censo 2022, o vazamento de nomes no privacy-filter-br caiu de 15,4% para 1,4%. Nomes sem contexto e de outras origens ainda passam; o detector spaCy ajuda, mas deixa o Véu mais de dez vezes mais lento.
- **Endereços completos e contas sem a palavra "conta"** ainda vazam no BR-Agentic.
- **Todos os textos são sintéticos.** Em dados reais, espere resultados piores. Teste com uma amostra dos seus textos (`veu avaliar --dataset`).

Detalhes da metodologia em [docs/benchmark.md](docs/benchmark.md).

## Configuração

Quem usa o painel não precisa editar nada: as caixinhas gravam a configuração. Quem preferir pode escrever um `veu.toml` (exemplo completo em [examples/veu.toml](examples/veu.toml)):

```toml
[deteccao]
limiar = 0.5                                   # 0 a 1; mais alto = menos falsos positivos
ignorar = ["contato@minhaempresa.example"]      # valores que nunca são escondidos

[anonimizacao]
operador = "token"

[politica]
bloquear = ["CARTAO_CREDITO", "CHAVE_PRIVADA"] # recusa o pedido em vez de só esconder

[restauracao]
links = false                                  # dados reais nunca voltam dentro de links e URLs
segredos_em_ferramentas = false                # chaves e senhas não voltam nos argumentos de ferramentas

[servidor]
log_auditoria = "veu-auditoria.jsonl"          # só contagens, nunca os valores, em cadeia de hashes
```

O painel guarda o arquivo em `%APPDATA%\veu\veu.toml` no Windows, `~/Library/Application Support/veu/veu.toml` no Mac e `~/.config/veu/veu.toml` no Linux. Equipes, sessões no Redis, desvio para modelo interno e leitura de links do Notion estão no [guia para empresas](docs/empresas.md).

## Segurança

- **Acesso:**
  - o Véu ouve só em `127.0.0.1` por padrão e recusa pedidos de outros sites abertos no navegador (CSRF e DNS rebinding);
  - fora do computador local, ele **não inicia sem token**;
  - cada equipe pode ter o seu token e a sua política.
- **Restauração:**
  - a resposta da IA nunca recebe os dados reais dentro de links, imagens, URLs ou atributos HTML, nem em streaming;
  - chaves, tokens e senhas não voltam nos argumentos das ferramentas de agentes;
  - marcadores que chegam escritos por terceiros são desarmados antes do envio;
  - no MCP, a ferramenta que devolve os dados reais para a conversa vem desligada.
- **Dados:**
  - se a detecção falhar, a requisição não sai;
  - o cofre fica na memória (ou no seu Redis, cifrado com AES-256-GCM) e expira sem uso;
  - a leitura de links do proxy só acessa endereços públicos, também nos redirecionamentos;
  - a página web e a extensão não enviam nada pela internet;
  - o painel só funciona no próprio computador.
- **Auditoria:** o log tem só contagens (do que foi escondido e do que voltou), em cadeia de hashes (HMAC com segredo). `veu auditoria verificar` aponta linhas alteradas ou removidas, e a âncora (`veu auditoria ancorar`) acusa linhas apagadas no fim.
- **Limites:** o Véu protege os dados da IA, mas não decide quem pode ver o quê dentro do seu sistema. Veja as [limitações](SECURITY.md#o-que-o-véu-não-faz).

Leia o [modelo de ameaças](docs/modelo-de-ameacas.md) e as [limitações](SECURITY.md) antes de usar em produção.

## Desenvolvimento

```bash
git clone https://github.com/guhttps/veu && cd veu
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # 570 testes, inclusive com os SDKs oficiais, LangChain, MCP, Office e Redis
ruff check .
veu avaliar               # benchmark
VEU_HIPOTESES=5000 pytest tests/test_propriedades.py   # testes de propriedade com uma busca longa
cd js && npm ci && npm test                       # biblioteca JavaScript (inclui a conformidade com o Python)
node extensao/teste/e2e.mjs                        # extensão e página num Chrome de verdade
```

Veja o [guia de contribuição](CONTRIBUTING.md). Contribuições de nomes, padrões de documentos, formatos de chaves e casos difíceis são muito bem-vindas.

## Próximos passos

- [x] Publicar no PyPI (`pip install veu`) e no npm (`@guhttps/veu`)
- [x] Instalador de um comando e painel para quem não programa
- [x] Restauração segura contra injeção de prompt (links, ferramentas, marcadores forjados)
- [x] Benchmark com dados em português de terceiros, comparado ao Presidio
- [x] Cache de detecção para agentes que reenviam a conversa inteira a cada turno
- [x] Nó para o n8n (WhatsApp com IA sem expor o CPF do cliente)
- [x] Documentos de Portugal e da América Latina (CUIT, CURP, RFC, RUT, NIT, RUC, RIF e cédulas)
- [ ] Documentos de Angola, Moçambique, Estados Unidos e Europa; MRZ de passaporte, VIN e carteiras de criptomoeda
- [ ] Nomes de outras línguas sem precisar de modelo
- [ ] Abrir Excel e Word direto na página web, sem instalar nada
- [ ] Operador sintético na versão JavaScript
- [ ] Bibliotecas para Go e Java
- [ ] Mais casos difíceis escritos à mão, de domínios reais (com dados fictícios)
- [ ] Detector de nomes em minúsculas sem saudação ("o rayane esqueceu")

## Licença

[MIT](LICENSE). Os dados usados nos exemplos e no benchmark são fictícios. As listas de nomes e municípios vêm do IBGE (Censo Demográfico 2022, Nomes do Brasil, e Localidades), dados públicos.
