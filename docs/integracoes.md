# Integrações

Há três jeitos de usar o Véu, e eles podem ser combinados:

| Jeito | Para quem | O que muda no seu código |
|---|---|---|
| **Proxy** (`veu servir`) | Qualquer linguagem e ferramenta que fale HTTP | Só a URL base do SDK |
| **Transporte HTTP** (`veu.integrations`) | Aplicações Python | Como o cliente do SDK é criado |
| **Biblioteca e API REST** | Fluxos próprios, n8n, filas, ETL | Você chama `anonimizar` e `restaurar` |

Cada seção abaixo diz se a integração é coberta pelos testes automatizados do projeto.

- [OpenAI](#openai)
- [Anthropic](#anthropic)
- [Gemini](#gemini)
- [Provedores compatíveis com OpenAI](#provedores-compatíveis-com-openai)
- [LangChain](#langchain)
- [Node.js e outras linguagens](#nodejs-e-outras-linguagens)
- [API REST (n8n, Make, qualquer linguagem)](#api-rest-n8n-make-qualquer-linguagem)
- [Logs](#logs)
- [pre-commit e CI](#pre-commit-e-ci)
- [Linha de comando](#linha-de-comando)
- [Docker](#docker)
- [Sessões](#sessões)

## OpenAI

*Coberto pelos testes: proxy e transporte, com o SDK oficial `openai`, com e sem streaming, síncrono e assíncrono.*

Pelo proxy:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1")   # OPENAI_API_KEY continua igual
```

Sem proxy, dentro do processo:

```python
from veu.integrations.sdk import openai_client, async_openai_client

client = openai_client()                 # aceita os mesmos argumentos de openai.OpenAI
aclient = async_openai_client()
```

Endpoints cobertos: `chat/completions` (inclusive `tool_calls`), `responses`, `embeddings` e `completions`.

## Anthropic

*Coberto pelos testes: proxy e transporte, com o SDK oficial `anthropic`, inclusive streaming.*

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://127.0.0.1:8787")    # o SDK chama /v1/messages
```

Ou, sem proxy:

```python
from veu.integrations.sdk import anthropic_client

client = anthropic_client()
```

Textos, documentos de texto, `tool_use` e `tool_result` são protegidos. Blocos de `thinking` não são alterados, porque são assinados pela Anthropic e qualquer mudança invalidaria a assinatura.

## Gemini

*Coberto pelos testes: o formato nativo (generateContent e streamGenerateContent) pelo proxy. O SDK `google-genai` não é testado automaticamente.*

Pela API nativa:

```bash
curl "http://127.0.0.1:8787/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Sou a Maria Souza, CPF 529.982.247-25"}]}]}'
```

Com o SDK `google-genai`, aponte a URL base para o Véu:

```python
from google import genai
from google.genai import types

client = genai.Client(http_options=types.HttpOptions(base_url="http://127.0.0.1:8787"))
```

Pela compatibilidade com OpenAI do próprio Gemini: `OpenAI(base_url="http://127.0.0.1:8787/gemini-openai/v1", api_key=GEMINI_API_KEY)`.

## Provedores compatíveis com OpenAI

*Coberto pelos testes: o roteamento por prefixo.*

Use o nome do provedor como prefixo no caminho:

| Provedor | URL base para o SDK |
|---|---|
| OpenAI | `http://127.0.0.1:8787/v1` |
| Groq | `http://127.0.0.1:8787/groq/v1` |
| OpenRouter | `http://127.0.0.1:8787/openrouter/v1` |
| DeepSeek | `http://127.0.0.1:8787/deepseek/v1` |
| Mistral | `http://127.0.0.1:8787/mistral/v1` |
| Together | `http://127.0.0.1:8787/together/v1` |
| Maritaca (Sabiá) | `http://127.0.0.1:8787/maritaca/v1` |
| Gemini (compatível com OpenAI) | `http://127.0.0.1:8787/gemini-openai/v1` |
| Ollama local | `http://127.0.0.1:8787/ollama/v1` |
| LM Studio local | `http://127.0.0.1:8787/lmstudio/v1` |

Para um provedor que não está na lista (vLLM, Azure, uma API interna), adicione no `veu.toml`:

```toml
[provedores.interno]
tipo = "openai"                       # "openai", "anthropic" ou "gemini"
url = "https://ia.minhaempresa.com/v1"
```

E use `http://127.0.0.1:8787/interno/v1`. Para trocar o provedor de `/v1`, use `provedor_padrao` em `[servidor]`.

## LangChain

*Não coberto pelos testes automatizados.* O jeito mais simples é apontar a URL base para o proxy:

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

modelo = ChatOpenAI(model="gpt-4o-mini", base_url="http://127.0.0.1:8787/v1")
claude = ChatAnthropic(model="claude-sonnet-4-5", base_url="http://127.0.0.1:8787")
```

O mesmo vale para o LlamaIndex (`api_base`) e para qualquer framework que permita trocar a URL do provedor.

## Node.js e outras linguagens

*Não coberto pelos testes automatizados; usa o proxy, que é coberto.*

```javascript
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";

const openai = new OpenAI({ baseURL: "http://127.0.0.1:8787/v1" });
const claude = new Anthropic({ baseURL: "http://127.0.0.1:8787" });
```

Go, Java, C#, PHP e Ruby funcionam do mesmo jeito: troque a URL base do cliente.

## API REST (n8n, Make, qualquer linguagem)

*Coberto pelos testes.*

Quando o modelo de IA não é chamado por HTTP direto (por exemplo, um nó pronto do n8n), proteja o texto antes e restaure depois:

```bash
# 1. Esconder: guarde a "sessao" da resposta
curl -s http://127.0.0.1:8787/veu/v1/anonimizar -H "Content-Type: application/json" \
  -d '{"texto": "Sou a Maria Souza, CPF 529.982.247-25"}'
# {"texto": "Sou a [PESSOA_1], CPF [CPF_1]", "sessao": "k3J...", "substituicoes": [...]}

# 2. Mande o texto para a IA como quiser.

# 3. Restaurar a resposta com a mesma sessão
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

No n8n: um nó **HTTP Request** para `/veu/v1/anonimizar`, o nó de IA usando `{{$json.texto}}` e outro **HTTP Request** para `/veu/v1/restaurar` com a `sessao` do primeiro nó. Veja [examples/n8n.md](../examples/n8n.md).

## Logs

*Coberto pelos testes.*

Logs costumam ser o lugar onde dados pessoais vazam sem ninguém perceber:

```python
import logging
from veu.integrations.logging import protect_logs

logging.basicConfig(level=logging.INFO)
protect_logs()                                      # em todos os handlers do logger raiz

logging.info("Cliente %s, CPF %s", "Maria Souza", "529.982.247-25")
# INFO:root:Cliente [PESSOA], CPF [CPF]
```

O filtro também esconde dados nos tracebacks das exceções. Use `operator="mascara"` para manter parte do valor (`***.982.247-**`).

## pre-commit e CI

*Coberto pelos testes (o comando `veu verificar`).*

Impede que CPFs, e-mails e outros dados reais entrem no repositório. Em `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/guhttps/veu
    rev: v0.1.0
    hooks:
      - id: veu
```

Linhas com dados fictícios propositais podem ser liberadas com o comentário `veu: ignorar`. No CI, rode direto:

```bash
veu verificar $(git ls-files '*.py' '*.md' '*.json')
```

A saída mostra o arquivo, a linha e o valor **mascarado**, para não repetir o dado no log do CI.

## Linha de comando

```bash
veu detectar contrato.txt                         # lista os dados encontrados
veu anonimizar contrato.txt --cofre cofre.json -o contrato-anonimo.txt
veu restaurar resposta.txt --cofre cofre.json     # devolve os dados reais
cat conversa.txt | veu anonimizar --operador mascara
veu entidades                                     # tipos suportados
```

O arquivo do cofre contém os dados reais: guarde com cuidado e não versione.

## Docker

```bash
docker build -t veu .
docker run -p 8787:8787 -e VEU_TOKEN=troque-este-valor veu
```

Dentro do contêiner o Véu ouve em `0.0.0.0`, por isso o token é recomendado: com ele, todas as rotas (menos `/veu/saude`) exigem o cabeçalho `X-Veu-Token`. Para usar um `veu.toml`, monte o arquivo e aponte `VEU_CONFIG` para ele.

## Sessões

Por padrão, cada requisição tem seu próprio cofre. Para manter os mesmos marcadores entre requisições diferentes (por exemplo, embeddings e chat da mesma conversa), envie o cabeçalho `X-Veu-Sessao` com um identificador seu. As sessões ficam na memória e expiram após uma hora sem uso (`sessao_ttl`).
