# Véu no n8n

Quando o fluxo usa um nó de IA pronto (OpenAI, Anthropic, Gemini, "AI Agent"), proteja o texto com a API REST do Véu antes do nó e restaure a resposta depois.

Pré-requisito: o Véu rodando e acessível pelo n8n, por exemplo com Docker na mesma rede:

```bash
docker run -d --name veu --network n8n -e VEU_TOKEN=troque-este-valor veu
```

## Fluxo

```text
[Gatilho] → [HTTP Request: anonimizar] → [Nó de IA] → [HTTP Request: restaurar] → [Resposta]
```

### 1. HTTP Request "Esconder dados"

- Método: `POST`
- URL: `http://veu:8787/veu/v1/anonimizar`
- Cabeçalho: `X-Veu-Token: troque-este-valor`
- Corpo (JSON): `{"texto": "{{ $json.mensagem }}"}`

A resposta traz `texto` (já com os marcadores) e `sessao`.

### 2. Nó de IA

Use `{{ $json.texto }}` como mensagem do usuário. No prompt de sistema, vale incluir:

> Os marcadores entre colchetes, como [PESSOA_1], substituem dados pessoais. Repita-os exatamente como estão.

### 3. HTTP Request "Restaurar dados"

- Método: `POST`
- URL: `http://veu:8787/veu/v1/restaurar`
- Cabeçalho: `X-Veu-Token: troque-este-valor`
- Corpo (JSON):

```json
{
  "texto": "{{ $json.output }}",
  "sessao": "{{ $('Esconder dados').item.json.sessao }}"
}
```

Troque `$json.output` pelo campo onde o seu nó de IA devolve o texto.

## Alternativa: nó de IA apontando para o proxy

Se o nó permitir trocar a URL base da API (credenciais "OpenAI" com Base URL personalizada, por exemplo), use `http://veu:8787/v1`. Aí o Véu esconde e restaura sozinho, sem os dois nós HTTP.

Com `VEU_TOKEN` definido, o nó precisa enviar o cabeçalho `X-Veu-Token`. Se ele não permitir cabeçalhos extras, rode o Véu sem token (`-e VEU_PERMITIR_SEM_TOKEN=1`), mas só na rede interna do Docker: não publique a porta (`-p`) para fora.
