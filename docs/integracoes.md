# Integrações

O Véu se encaixa em vários pontos. Escolha pelo que você já usa; as opções podem ser combinadas.

| Jeito | Para quem | O que muda no seu código |
|---|---|---|
| **Navegador** | Quem usa ChatGPT, Claude ou Gemini pelo site | Nada: [página](https://guhttps.github.io/veu/) ou [extensão](extensao.md) |
| **Proxy** (`veu servir`) | Qualquer linguagem, framework ou ferramenta que fale HTTP | Só a URL base do SDK |
| **Dentro do Python** | Aplicações Python (SDKs, LangChain, qualquer função) | Uma linha na criação do cliente ou um decorador |
| **Dentro do JavaScript** | Node, Deno, Bun, navegador, AI SDK da Vercel | `fetch: createFetch()` ou um middleware |
| **Agentes** | Claude Code, Claude Desktop, Cursor | Nada: plugin, ganchos e ferramentas MCP |
| **Fontes** | Notion, Google Docs/Sheets/Slides, links, Word, Excel, PowerPoint, PDF | `veu ler` ou a ferramenta `ler_protegido` |
| **Dados** | Arquivos CSV/JSON/JSONL/Excel, pandas, bases de RAG | Um comando ou uma função |
| **Empresas** | Gateway central, LiteLLM, extensão gerenciada | Veja o [guia para empresas](empresas.md) |
| **Observabilidade** | Logs, Sentry, Prometheus | Um filtro ou processador |
| **Repositórios** | pre-commit, GitHub Actions, aba Security | Um arquivo de configuração |

Cada seção diz se a integração é coberta pelos testes automatizados do projeto.

**Modelos de IA:**
[OpenAI](#openai) ·
[Anthropic](#anthropic) ·
[Gemini](#gemini) ·
[Ollama](#ollama) ·
[Outros provedores](#provedores-compatíveis-com-openai) ·
[Azure OpenAI](#azure-openai) ·
[Regras por provedor](#regras-por-provedor) ·
[Opções por requisição](#opções-por-requisição)

**Python:**
[Atalhos dos SDKs](#atalhos-dos-sdks) ·
[LangChain](#langchain) ·
[Decorador @protect](#decorador-protect) ·
[Sessão](#sessão) ·
[Biblioteca](#biblioteca)

**Agentes, linguagens e no-code:**
[MCP](#mcp-claude-code-claude-desktop-cursor) ·
[Claude Code e Cursor](#claude-code-e-cursor) ·
[JavaScript e TypeScript](#javascript-e-typescript) ·
[API REST e n8n](#api-rest-n8n-make-qualquer-linguagem)

**Fontes:**
[Notion, Google e documentos](#notion-google-e-documentos) ·
[Links no proxy](#links-no-proxy)

**Dados:**
[Arquivos](#arquivos-csv-json-jsonl-e-office) ·
[pandas](#pandas) ·
[RAG](#rag)

**Observabilidade:**
[logging](#logging) ·
[structlog](#structlog) ·
[loguru](#loguru) ·
[Sentry](#sentry) ·
[Prometheus](#prometheus)

**Repositórios:**
[pre-commit](#pre-commit) ·
[GitHub Action](#github-action) ·
[SARIF](#sarif-e-aba-security)

**Extensões e implantação:**
[Detectores próprios](#detectores-próprios) ·
[Exceções](#exceções) ·
[Docker](#docker) ·
[Sessões do proxy](#sessões-do-proxy)

---

## Modelos de IA

### OpenAI

*Coberto pelos testes: proxy e transporte, com o SDK oficial, com e sem streaming, síncrono e assíncrono.*

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1")   # OPENAI_API_KEY continua igual
```

Endpoints protegidos: `chat/completions` (inclusive `tool_calls`), `responses`, `embeddings` e `completions`.

### Anthropic

*Coberto pelos testes: proxy e transporte, com o SDK oficial, inclusive streaming.*

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://127.0.0.1:8787")    # o SDK chama /v1/messages
```

Textos, documentos de texto, `tool_use` e `tool_result` são protegidos. Blocos de `thinking` não são alterados, porque são assinados pela Anthropic.

### Gemini

*Coberto pelos testes: formato nativo (generateContent e streamGenerateContent) pelo proxy. O SDK `google-genai` não é testado automaticamente.*

```bash
curl "http://127.0.0.1:8787/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Sou a Maria Souza, CPF 529.982.247-25"}]}]}'
```

```python
from google import genai
from google.genai import types

client = genai.Client(http_options=types.HttpOptions(base_url="http://127.0.0.1:8787"))
```

Também dá para usar a compatibilidade com OpenAI do próprio Gemini: `OpenAI(base_url="http://127.0.0.1:8787/gemini-openai/v1")`.

### Ollama

*Coberto pelos testes: a API nativa pelo proxy (`/api/chat`, `/api/generate`, `/api/embed`), inclusive o streaming em JSON por linha. O cliente `ollama` em Python não é testado automaticamente.*

O Véu entende tanto a API compatível com OpenAI (`/ollama/v1/...`) quanto a nativa. Para clientes que falam com o Ollama direto (Open WebUI, scripts com a biblioteca `ollama`), aponte o host para o Véu:

```python
import ollama

client = ollama.Client(host="http://127.0.0.1:8787/ollama")
client.chat(model="llama3.2", messages=[{"role": "user", "content": "Sou a Maria Souza, CPF 529.982.247-25"}])
```

Se o Ollama roda na sua própria máquina, os dados nem saem dela: veja como [desligar a anonimização só para ele](#regras-por-provedor). Para um Ollama em outro servidor, ajuste a URL com `VEU_URL_OLLAMA=http://servidor-gpu:11434`.

### Provedores compatíveis com OpenAI

*Coberto pelos testes: o roteamento por prefixo.*

Use o nome do provedor como prefixo no caminho da URL base do SDK:

| Provedor | URL base | Chave (com `injetar_chaves`) |
|---|---|---|
| OpenAI | `http://127.0.0.1:8787/v1` | `OPENAI_API_KEY` |
| Groq | `http://127.0.0.1:8787/groq/v1` | `GROQ_API_KEY` |
| OpenRouter | `http://127.0.0.1:8787/openrouter/v1` | `OPENROUTER_API_KEY` |
| DeepSeek | `http://127.0.0.1:8787/deepseek/v1` | `DEEPSEEK_API_KEY` |
| Mistral | `http://127.0.0.1:8787/mistral/v1` | `MISTRAL_API_KEY` |
| Together | `http://127.0.0.1:8787/together/v1` | `TOGETHER_API_KEY` |
| xAI (Grok) | `http://127.0.0.1:8787/xai/v1` | `XAI_API_KEY` |
| Perplexity | `http://127.0.0.1:8787/perplexity/v1` | `PERPLEXITY_API_KEY` |
| Fireworks | `http://127.0.0.1:8787/fireworks/v1` | `FIREWORKS_API_KEY` |
| Cerebras | `http://127.0.0.1:8787/cerebras/v1` | `CEREBRAS_API_KEY` |
| Hugging Face | `http://127.0.0.1:8787/huggingface/v1` | `HF_TOKEN` |
| Cohere | `http://127.0.0.1:8787/cohere/v1` | `COHERE_API_KEY` |
| NVIDIA NIM | `http://127.0.0.1:8787/nvidia/v1` | `NVIDIA_API_KEY` |
| SambaNova | `http://127.0.0.1:8787/sambanova/v1` | `SAMBANOVA_API_KEY` |
| Maritaca (Sabiá) | `http://127.0.0.1:8787/maritaca/v1` | `MARITACA_API_KEY` |
| Gemini (compatível com OpenAI) | `http://127.0.0.1:8787/gemini-openai/v1` | `GEMINI_API_KEY` |
| Ollama local | `http://127.0.0.1:8787/ollama/v1` | — |
| LM Studio local | `http://127.0.0.1:8787/lmstudio/v1` | — |
| vLLM local | `http://127.0.0.1:8787/vllm/v1` | — |
| llama.cpp local | `http://127.0.0.1:8787/llamacpp/v1` | — |

Para um provedor que não está na lista (uma API interna, por exemplo), adicione no `veu.toml` e use `http://127.0.0.1:8787/interno/v1`:

```toml
[provedores.interno]
tipo = "openai"                       # "openai", "anthropic", "gemini" ou "ollama"
url = "https://ia.minhaempresa.example/v1"
chave_env = "IA_INTERNA_KEY"
```

Para trocar a URL de um provedor pronto sem editar o arquivo: `VEU_URL_GROQ=https://...`. Para mudar quem atende `/v1` sem prefixo: `provedor_padrao` em `[servidor]`.

### Azure OpenAI

*Não coberto pelos testes automatizados.* Cadastre o seu recurso como provedor próprio e aponte o cliente `AzureOpenAI` para o Véu:

```toml
[provedores.azure]
tipo = "openai"
url = "https://MEU-RECURSO.openai.azure.com"
```

```python
from openai import AzureOpenAI

client = AzureOpenAI(azure_endpoint="http://127.0.0.1:8787/azure", api_key=AZURE_KEY, api_version="2024-10-21")
client.chat.completions.create(model="MEU-DEPLOYMENT", messages=[...])
```

O SDK chama `/azure/openai/deployments/MEU-DEPLOYMENT/chat/completions`, que o Véu protege e repassa ao seu recurso com o cabeçalho `api-key`.

### Regras por provedor

*Coberto pelos testes.*

Cada provedor pode ter regras próprias, inclusive os que já vêm prontos:

```toml
[provedores.ollama]
anonimizar = false                     # modelo local: os dados não saem da máquina

[provedores.openrouter]
operador = "sintetico"                 # valores realistas em vez de [CPF_1]
bloquear = ["CARTAO_CREDITO", "CNS"]   # recusa a requisição se tiver esses dados
```

### Opções por requisição

*Coberto pelos testes.*

| Cabeçalho | Efeito |
|---|---|
| `X-Veu-Sessao: <id>` | Mantém os mesmos marcadores entre requisições ([sessões](#sessões-do-proxy)) |
| `X-Veu-Operador: sintetico` | Escolhe o operador só desta requisição (desligue com `operador_por_requisicao = false`) |
| `X-Veu-Token: <token>` | Obrigatório quando o servidor tem `VEU_TOKEN` |

As respostas trazem `X-Veu-Entidades` (quantos dados de cada tipo foram escondidos) e, quando a política recusa, `X-Veu-Bloqueado`.

---

## Python

### Atalhos dos SDKs

*Coberto pelos testes, com os SDKs oficiais (que usam `httpx2`).*

Sem subir o proxy: o próprio processo esconde e restaura.

```python
from veu.integrations.sdk import openai_client, anthropic_client, async_openai_client, async_anthropic_client

client = openai_client()          # mesmos argumentos de openai.OpenAI(...)
claude = anthropic_client()       # mesmos argumentos de anthropic.Anthropic(...)
```

Para qualquer outro SDK que aceite um cliente HTTP, use o transporte: `veu.integrations.httpx2.VeuTransport` (OpenAI 3.x, Anthropic 2.x) ou `veu.integrations.httpx.VeuTransport` (Groq, Mistral e SDKs que usam o `httpx`).

### LangChain

*Coberto pelos testes, com `langchain-core` (`pip install "veu[langchain]"`).*

Integração nativa: funciona com qualquer modelo ou cadeia, em qualquer posição.

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from veu.integrations.langchain import protect_model

modelo = protect_model(ChatOpenAI(model="gpt-4o-mini"))
cadeia = ChatPromptTemplate.from_template("Responda: {pergunta}") | modelo | StrOutputParser()
cadeia.invoke({"pergunta": "Sou a Maria Souza, CPF 529.982.247-25"})
```

Protege `invoke`, `ainvoke`, `stream` e `astream`, texto, listas de mensagens, prompts e argumentos de chamadas de ferramentas. Também dá para apontar o `base_url` do `ChatOpenAI`/`ChatAnthropic` para o proxy.

### Decorador @protect

*Coberto pelos testes.*

Para qualquer código que chama um modelo, com qualquer biblioteca (ou com `requests` direto):

```python
from veu import protect

@protect
def responder(pergunta: str, historico: list) -> str:
    return meu_llm.gerar(pergunta, historico)     # recebe [PESSOA_1], [CPF_1]...

responder("Sou a Maria Souza, CPF 529.982.247-25", [])   # devolve a resposta com os dados reais
```

Funciona com funções síncronas, `async`, geradoras e geradoras assíncronas (streaming). Opções: `arguments=["pergunta"]` limita quais parâmetros anonimizar; `restore=False` devolve a resposta ainda anônima.

### Sessão

*Coberto pelos testes.*

Para fluxos próprios: um cofre compartilhado por várias chamadas.

```python
import veu

with veu.session() as sessao:
    mensagens = sessao.anonymize_data([{"role": "user", "content": "Sou a Maria Souza"}])
    resposta = chamar_modelo(mensagens)
    print(sessao.restore(resposta))
    for pedaco in sessao.restore_stream(stream_do_modelo):     # também async: arestore_stream
        print(pedaco, end="")
```

### Biblioteca

```python
import veu

resultado = veu.anonymize("Sou a Maria Souza, CPF 529.982.247-25")
resultado.text                 # "Sou a [PESSOA_1], CPF [CPF_1]"
resultado.restore("Olá, [PESSOA_1]")
veu.analyze("...")             # só detectar
```

Para opções: `veu.Veu(operator="sintetico", threshold=0.6, allow_patterns=[...], extra_recognizers=[...])`.

---

## Agentes, linguagens e no-code

### MCP (Claude Code, Claude Desktop, Cursor)

*Coberto pelos testes, com o SDK oficial do MCP (`pip install "veu[mcp]"`).*

O servidor MCP dá ao agente ferramentas que **processam os arquivos na sua máquina e devolvem só contagens e valores mascarados**. O agente consegue auditar uma pasta ou gerar uma cópia anonimizada de uma planilha sem que os dados pessoais entrem na conversa.

```bash
claude mcp add veu -- veu mcp          # Claude Code
```

Claude Desktop e Cursor (`claude_desktop_config.json` ou `.cursor/mcp.json`):

```json
{ "mcpServers": { "veu": { "command": "veu", "args": ["mcp"] } } }
```

| Ferramenta | O que faz | O agente vê os dados? |
|---|---|---|
| `ler_protegido` | Lê um arquivo, uma página do Notion, um Google Docs/Sheets ou um link já com os dados trocados por marcadores | Só a versão protegida |
| `verificar_arquivo` | Lista os dados pessoais e segredos de um arquivo (linha, coluna, tipo), inclusive Word, Excel e PDF | Não: só valores mascarados |
| `anonimizar_arquivo` | Cria uma cópia anonimizada (texto, CSV, JSON, JSONL, Word, Excel, PowerPoint) | Não: só contagens |
| `restaurar_arquivo` | Restaura um arquivo com um cofre salvo | Não |
| `detectar` | Lista os dados pessoais de um texto | Não: só valores mascarados |
| `anonimizar_texto` | Troca os dados de um texto por marcadores | Só a versão anonimizada |
| `restaurar_texto` | Devolve os dados reais de uma sessão | **Sim** |
| `listar_entidades` | Tipos suportados | — |

Peça, por exemplo: "verifique se há dados pessoais em `dados/clientes.csv` e gere `dados/clientes-anonimo.csv` tratando a coluna cpf como CPF".

### Claude Code e Cursor

*Coberto pelos testes: ganchos, plugin (validado com `claude plugin validate`) e ferramentas MCP.*

O plugin junta três peças:

- **Ganchos:**
  - um prompt com chave de API, senha ou chave privada não é enviado;
  - um prompt com dados pessoais gera um aviso;
  - um arquivo com segredos não é lido. O agente recebe o motivo e a sugestão de usar `ler_protegido`.
- **Servidor MCP:** as ferramentas da tabela acima.
- **Skill `protecao-de-dados`:** ensina o agente a ler planilhas, documentos e páginas do Notion protegidos, a manter os marcadores e a nunca escrever segredos no código.

```text
/plugin install veu --marketplace guhttps/veu
```

O plugin chama o comando `veu`, que precisa estar instalado: `pipx install "veu[mcp,documentos]"`.

Sem o plugin, os ganchos também funcionam sozinhos, no `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "veu gancho prompt" }] }],
    "PreToolUse": [{ "matcher": "Read", "hooks": [{ "type": "command", "command": "veu gancho arquivo" }] }]
  }
}
```

Opções do gancho:

| Opção | Efeito |
|---|---|
| `--modo bloquear` | Também bloqueia prompts com dados pessoais (o padrão só avisa) |
| `--dados-pessoais permitir`, `perguntar` (padrão) ou `negar` | O que fazer com arquivos que têm dados pessoais, mas não segredos |
| `--bloquear CPF,CARTAO_CREDITO` | Troca a lista de tipos que sempre bloqueiam (padrão: os segredos) |

No **Cursor**, use o [`examples/cursor-hooks.json`](../examples/cursor-hooks.json) em `.cursor/hooks.json` (formato `--formato cursor`). O servidor MCP entra no `.cursor/mcp.json`, como acima.

A skill também pode ser usada sozinha. No Claude.ai, compacte a pasta `plugin/skills/protecao-de-dados` e envie em Configurações > Skills.

### JavaScript e TypeScript

*Coberto pelos testes, com os SDKs oficiais da OpenAI e da Anthropic e o AI SDK da Vercel.*

A biblioteca [`@guhttps/veu`](../js/README.md) traz a mesma detecção da versão em Python, sem dependências e sem servidor:

```ts
import OpenAI from "openai";
import { createFetch } from "@guhttps/veu/fetch";
import { wrapLanguageModel } from "ai";
import { veuMiddleware } from "@guhttps/veu/ai-sdk";

const openai = new OpenAI({ fetch: createFetch() });                       // também a Anthropic
const model = wrapLanguageModel({ model: openai("gpt-5-mini"), middleware: veuMiddleware() });
```

Outras linguagens (Go, Java, C#, PHP, Ruby) usam o proxy: troque a URL base do cliente para `http://127.0.0.1:8787/v1`.

### API REST (n8n, Make, qualquer linguagem)

*Coberto pelos testes.*

```bash
curl -s http://127.0.0.1:8787/veu/v1/anonimizar -H "Content-Type: application/json" \
  -d '{"texto": "Sou a Maria Souza, CPF 529.982.247-25"}'
# {"texto": "Sou a [PESSOA_1], CPF [CPF_1]", "sessao": "k3J...", "substituicoes": [...]}

curl -s http://127.0.0.1:8787/veu/v1/restaurar -H "Content-Type: application/json" \
  -d '{"texto": "Olá, [PESSOA_1]!", "sessao": "k3J..."}'
# {"texto": "Olá, Maria Souza!"}
```

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /veu/v1/detectar` | `{"texto"}` | `{"entidades": [...]}` |
| `POST /veu/v1/anonimizar` | `{"texto", "sessao"?, "operador"?}` | `{"texto", "sessao", "substituicoes"}` |
| `POST /veu/v1/restaurar` | `{"texto", "sessao"}` | `{"texto"}` |
| `GET /veu/saude` | — | `{"status": "ok"}` |
| `GET /veu/estatisticas` | — | contagens por entidade e provedor |
| `GET /veu/metricas` | — | métricas no formato do Prometheus |

A `sessao` é criada pelo servidor na primeira chamada; envie-a de volta para continuar. Guia do n8n em [examples/n8n.md](../examples/n8n.md).

---

## Notion, Google e documentos

*Coberto pelos testes, com respostas simuladas das APIs do Notion e do Google e documentos reais do Office e PDF.*

`veu ler` busca o conteúdo, converte para texto (Markdown, com tabelas) e já entrega protegido:

```bash
veu ler https://www.notion.so/empresa/Atendimento-1f2e3d4c5b6a79788796a5b4c3d2e1f0
veu ler https://docs.google.com/spreadsheets/d/1AbC.../edit#gid=0 --cofre cofre.json
veu ler contrato.pdf --json
veu ler https://site.example/politica-de-privacidade
```

| Fonte | Como acessar |
|---|---|
| **Notion** (páginas e bases de dados) | Crie uma [integração interna](https://www.notion.so/profile/integrations), compartilhe a página com ela (••• > Conexões) e defina `NOTION_TOKEN` |
| **Google Docs, Sheets e Slides** | Público pelo link: funciona sem nada. Privado: `GOOGLE_ACCESS_TOKEN` com um token OAuth de leitura do Drive |
| **Links** | Qualquer página HTML, texto, JSON ou documento por URL |
| **Word, Excel, PowerPoint e PDF** | Arquivos locais (`pip install "veu[documentos]"`) |

Com `--cofre`, a resposta da IA pode ser restaurada depois: `veu restaurar resposta.txt --cofre cofre.json`. Para agentes, a ferramenta MCP `ler_protegido` faz o mesmo.

### Links no proxy

*Coberto pelos testes.*

Com `expandir_links = true`, quando alguém manda um link do Notion ou do Google pelo proxy, o Véu lê o conteúdo com os tokens do servidor e o acrescenta à mensagem já protegido. O modelo recebe o conteúdo, e não só o link:

```toml
[servidor]
expandir_links = true
dominios_expandidos = ["notion.so", "notion.site", "docs.google.com", "wiki.minhaempresa.example"]
```

Só domínios da lista e só HTTPS são lidos, contra SSRF. O conteúdo fica em cache por 10 minutos, e argumentos de ferramentas não são expandidos.

## Dados

### Arquivos (CSV, JSON, JSONL e Office)

*Coberto pelos testes.*

Word, Excel e PowerPoint são anonimizados **no próprio formato**: a formatação, as tabelas, os cabeçalhos, os rodapés e as fórmulas continuam iguais, e só os dados mudam. Os metadados do arquivo (autor, por exemplo) também são protegidos. PDF sai como texto.

```bash
veu anonimizar planilha.xlsx --forcar cpf=CPF -o planilha-protegida.xlsx --cofre cofre.json
veu anonimizar contrato.docx -o contrato-protegido.docx --cofre cofre.json
veu restaurar resposta.docx --cofre cofre.json -o resposta-final.docx
veu anonimizar laudo.pdf -o laudo.txt
```

Um único cofre para o arquivo inteiro: o mesmo CPF vira o mesmo marcador em todas as linhas, então contagens, junções e análises continuam funcionando.

```bash
veu anonimizar clientes.csv --forcar cpf=CPF --forcar nome=PESSOA --cofre cofre.json -o clientes-anonimo.csv
veu anonimizar conversas.jsonl --campos mensagem,resposta -o conversas-anonimas.jsonl
veu restaurar clientes-anonimo.csv --cofre cofre.json -o clientes-de-volta.csv
```

- O formato vem da extensão (`.csv`, `.tsv`, `.json`, `.jsonl`) ou de `--formato`. O separador do CSV é detectado sozinho.
- `--campos` limita quais colunas ou chaves são analisadas.
- `--forcar campo=TIPO` trata a coluna inteira como aquele dado, mesmo sem formato reconhecível (um CPF sem pontuação e inválido, um nome sozinho).

Em Python: `veu.files.anonymize_file(origem, destino, force={"cpf": "CPF"})`.

### pandas

*Coberto pelos testes (`pip install "veu[pandas]"`).*

```python
from veu.integrations.pandas import anonymize_dataframe, restore_dataframe

anonimo, cofre = anonymize_dataframe(df, force={"cpf": "CPF"})     # colunas de texto por padrão
original = restore_dataframe(anonimo, cofre)
```

### RAG

*Coberto pelos testes.*

Indexe os documentos já anonimizados; o mesmo cofre restaura as respostas geradas a partir do índice.

```python
from veu.integrations.langchain import VeuDocumentTransformer

documentos, cofre = VeuDocumentTransformer().anonymize(documentos)
# indexe "documentos" no banco vetorial e guarde cofre.to_dict() em local seguro
```

---

## Observabilidade

Logs e relatórios de erro costumam vazar dados pessoais sem ninguém perceber. Todas as integrações abaixo usam o operador `remover` por padrão (`[CPF]`, `[PESSOA]`); passe `operator="mascara"` para manter parte do valor.

### logging

*Coberto pelos testes.*

```python
import logging
from veu.integrations.logging import protect_logs

logging.basicConfig(level=logging.INFO)
protect_logs()            # em todos os handlers do logger raiz; também esconde dados dos tracebacks
```

### structlog

*Coberto pelos testes.*

```python
import structlog
from veu.integrations.structlog import PIIProcessor

structlog.configure(processors=[PIIProcessor(), structlog.processors.JSONRenderer()])
```

### loguru

*Coberto pelos testes.*

```python
from loguru import logger
from veu.integrations.loguru import pii_patcher

logger.configure(patcher=pii_patcher())
```

### Sentry

*Coberto pelos testes (as funções; o envio ao Sentry não é testado).*

```python
import sentry_sdk
from veu.integrations.sentry import before_send, before_breadcrumb

sentry_sdk.init(dsn="...", before_send=before_send, before_breadcrumb=before_breadcrumb)
```

Esconde dados de mensagens, exceções, variáveis locais dos frames, breadcrumbs, `request` e `user`, sem mexer nos campos técnicos (versões, sistema, stack).

### Prometheus

*Coberto pelos testes.*

`GET /veu/metricas` expõe contadores por provedor e por tipo de dado, requisições bloqueadas e erros do provedor, sem nenhum valor pessoal. Com token, o Prometheus pode autenticar com `Authorization: Bearer <token>`:

```yaml
scrape_configs:
  - job_name: veu
    authorization: { credentials: "seu-token" }
    static_configs: [{ targets: ["veu:8787"] }]
    metrics_path: /veu/metricas
```

---

## Repositórios

### pre-commit

*Coberto pelos testes.*

```yaml
repos:
  - repo: https://github.com/guhttps/veu
    rev: v0.3.0
    hooks:
      - id: veu
```

Linhas com dados fictícios propositais podem ser liberadas com o comentário `veu: ignorar`.

### GitHub Action

*Coberto pelo CI do próprio Véu.*

```yaml
- uses: actions/checkout@v5
- uses: guhttps/veu@v0.3.0
  with:
    limiar: "0.6"              # opcional
    caminhos: "src docs"       # opcional; padrão: todos os arquivos versionados
    sarif: veu.sarif           # opcional; para a aba Security
```

Os achados aparecem como anotações no pull request, com os valores mascarados. Entradas: `caminhos`, `diretorio`, `limiar`, `entidades`, `sarif`, `falhar` e `python-version`. Saída: `encontrados`.

### SARIF e aba Security

Com o relatório SARIF, os achados aparecem na aba **Security → Code scanning** do repositório:

```yaml
- uses: guhttps/veu@v0.3.0
  with: { sarif: veu.sarif, falhar: "false" }
- uses: github/codeql-action/upload-sarif@v4
  with: { sarif_file: veu.sarif }
```

Fora do GitHub: `veu verificar $(git ls-files) --formato sarif --saida veu.sarif` (também `github` e `json`).

---

## Extensões e implantação

### Detectores próprios

*Coberto pelos testes.*

Um detector é qualquer objeto com `name`, `labels` e `find(texto)`, que devolve candidatos:

```python
from veu.recognizers import Candidate

class Matricula:
    name = "matricula"
    labels = frozenset({"MATRICULA"})

    def find(self, texto):
        for inicio in encontrar_matriculas(texto):
            yield Candidate("MATRICULA", inicio, inicio + 10, 0.9, self.name)
```

Três jeitos de ligar:

- No código: `Veu(extra_recognizers=[Matricula()])`.
- No `veu.toml`, pelo caminho de importação: `detectores = ["padroes", "nomes", "enderecos", "meu_pacote.detectores:Matricula"]`.
- Como plugin de um pacote seu, pelo entry point `veu.detectores` no `pyproject.toml` (`matricula = "meu_pacote.detectores:Matricula"`); depois, `detectores = [..., "matricula"]`.

Para casos simples, um padrão no `veu.toml` basta: veja `[[deteccao.personalizados]]` em [examples/veu.toml](../examples/veu.toml).

### Exceções

```toml
[deteccao]
ignorar = ["11.222.333/0001-81"]                       # valores exatos
ignorar_padroes = ['@minhaempresa\.com\.br$', '^0800']   # expressões regulares
```

### LiteLLM

*Coberto pelos testes, com o LiteLLM instalado (`pip install "veu[litellm]"`).*

Se a empresa já usa o LiteLLM Proxy, o Véu entra como guardrail, sem proxy novo:

```yaml
guardrails:
  - guardrail_name: veu
    litellm_params:
      guardrail: veu.integrations.litellm.VeuGuardrail
      mode: [pre_call, post_call]
      default_on: true
```

Detalhes no [guia para empresas](empresas.md#litellm).

### Docker

```bash
docker build -t veu .
docker run -p 8787:8787 -e VEU_TOKEN=troque-este-valor veu
```

Dentro do contêiner o Véu ouve em `0.0.0.0`, por isso ele **não inicia sem `VEU_TOKEN`**: com o token, todas as rotas (menos `/veu/saude`) exigem o cabeçalho `X-Veu-Token`. Numa rede interna isolada, sem publicar a porta, dá para liberar o uso sem token com `-e VEU_PERMITIR_SEM_TOKEN=1`. Para usar um `veu.toml`, monte o arquivo e aponte `VEU_CONFIG` para ele.

### Sessões do proxy

Por padrão, cada requisição tem seu próprio cofre. Para manter os mesmos marcadores entre requisições (por exemplo, embeddings e chat da mesma conversa), envie `X-Veu-Sessao` com um identificador seu, um por conversa. As sessões ficam na memória e expiram após uma hora sem uso (`sessao_ttl`).

As sessões são separadas pela credencial do cliente (a chave de API enviada): quem usa outra chave nunca acessa o mesmo cofre, mesmo repetindo o identificador.
