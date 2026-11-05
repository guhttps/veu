# Instruções para agentes de código (Codex, Claude Code e outros)

O Véu esconde dados pessoais brasileiros antes de textos irem para modelos de IA e restaura as respostas. Leia o README para a visão geral.

## Comandos

```bash
pip install -e ".[dev]"           # ambiente (Python 3.11+)
pytest                             # todos os testes; precisam passar
ruff check .                       # lint; precisa passar
veu avaliar                        # benchmark; o vazamento da validação não pode piorar
```

No Windows, o ambiente virtual fica em `.venv/Scripts/`.

## Estrutura

- `src/veu/recognizers/`: detectores (padrões, nomes, endereços, spaCy, LLM local).
- `src/veu/analyzer.py`: junta detectores e resolve sobreposições.
- `src/veu/anonymizer.py` e `vault.py`: operadores, cofre e restauração (inclusive em streaming).
- `src/veu/gateway/`: formatos das APIs de IA (adaptadores e SSE), compartilhados pelo proxy e pelos transportes.
- `src/veu/server/`: proxy Starlette, API REST e playground.
- `src/veu/integrations/`: transportes httpx/httpx2, atalhos de SDK e filtro de logging.
- `src/veu/bench/`: gerador de dados anotados e avaliação.

## Regras

- Nunca use dados pessoais reais em código, testes, exemplos ou commits. Gere valores com `veu.surrogates`.
- Não ajuste o detector olhando `VALIDATION_TEMPLATES` em `bench/generator.py`: esse conjunto mede a generalização.
- Toda correção de detecção vem com um teste que falharia sem ela.
- Identificadores em inglês; textos para o usuário, chaves do `veu.toml` e comandos da CLI em português do Brasil.
- O núcleo (`veu` sem extras) não pode ganhar dependências. Servidor e integrações usam extras opcionais.
- Commits em inglês, no imperativo. Registre mudanças visíveis no `CHANGELOG.md`.
