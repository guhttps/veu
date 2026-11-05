# Changelog

Todas as mudanças relevantes ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [0.1.0] - 2026-11-04

Primeira versão.

### Detecção
- 21 tipos de dados brasileiros, com validação de dígitos verificadores de CPF, CNPJ (numérico e alfanumérico), PIS, CNS, CNH, título de eleitor, RENAVAM, processo CNJ e cartões (Luhn).
- Nomes de pessoas por listas de nomes brasileiros, capitalização e contexto, sem modelo de linguagem; detectores opcionais com spaCy e com um modelo local compatível com OpenAI.
- Endereços com logradouro, nome, número e complemento.
- Limiar de pontuação, lista de valores permitidos e padrões personalizados.

### Anonimização
- Operadores `token`, `sintetico`, `mascara`, `remover` e `hash`, configuráveis por tipo de dado.
- Cofre reversível, com o mesmo marcador para grafias diferentes do mesmo valor e ligação de nomes parciais ao nome completo.
- Restauração tolerante a marcadores reescritos pelo modelo e restauração em streaming.

### Integrações
- Proxy para OpenAI (Chat Completions, Responses, Embeddings e Completions), Anthropic (Messages) e Gemini (generateContent e streamGenerateContent), com e sem streaming.
- Atalhos para Groq, OpenRouter, DeepSeek, Mistral, Together, Maritaca, Ollama, LM Studio e o Gemini compatível com OpenAI, além de provedores próprios.
- Transportes para `httpx` e `httpx2` e atalhos `openai_client()` e `anthropic_client()`.
- API REST, playground, filtro de `logging`, hook de pre-commit, CLI e Dockerfile.
- Política de bloqueio por tipo de dado, sessões, token de acesso, estatísticas e log de auditoria só com contagens.

### Benchmark
- Gerador de textos anotados com dados falsos, conjuntos de desenvolvimento, validação e casos difíceis, e o comando `veu avaliar`.

[Unreleased]: https://github.com/guhttps/veu/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/guhttps/veu/releases/tag/v0.1.0
