#!/usr/bin/env bash
# Exemplos de chamadas pelo proxy. Antes: veu servir
set -euo pipefail
VEU=http://127.0.0.1:8787

# OpenAI (Chat Completions)
curl -s "$VEU/v1/chat/completions" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Sou a Maria Souza, CPF 529.982.247-25. Diga olá."}]}'

# Groq (qualquer provedor compatível com OpenAI: troque o prefixo)
curl -s "$VEU/groq/v1/chat/completions" \
  -H "Authorization: Bearer $GROQ_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Meu telefone é (11) 91234-5678."}]}'

# Anthropic
curl -s "$VEU/v1/messages" \
  -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-5", "max_tokens": 200, "messages": [{"role": "user", "content": "Sou o Carlos Lima, CNPJ 11.222.333/0001-81."}]}'

# Gemini (API nativa)
curl -s "$VEU/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Meu e-mail é ana.lima@example.com."}]}]}'

# Só ver o que seria escondido
curl -s "$VEU/veu/v1/detectar" -H "Content-Type: application/json" \
  -d '{"texto": "Sou a Maria Souza, CPF 529.982.247-25"}'
