# Instruções para agentes de código (Codex, Claude Code e outros)

O Véu esconde dados pessoais e segredos antes de textos irem para modelos de IA e restaura as respostas, com suporte completo a documentos brasileiros. Leia o README para a visão geral.

Mantenha o README em dia: toda mudança visível (recurso, integração, comando, número de testes, versão) atualiza o README no mesmo commit, e também o banner (`docs/banner.html` + `node docs/gerar-banner.mjs`) e a descrição do repositório quando mudarem.

## Comandos

```bash
pip install -e ".[dev]"           # ambiente (Python 3.11+)
pytest                             # todos os testes; precisam passar
ruff check .                       # lint; precisa passar
veu avaliar                        # benchmark; o vazamento da validação não pode piorar
python scripts/gerar_conformidade.py   # depois de mudar um detector: atualiza js/test/conformidade.json
cd js && npm ci && npm test        # versão JavaScript (precisa dar o mesmo resultado que a Python)
node extensao/teste/e2e.mjs        # extensão e página num Chrome de verdade
```

No Windows, o ambiente virtual fica em `.venv/Scripts/`.

## Estrutura

- `src/veu/recognizers/`: detectores (padrões, nomes, endereços, segredos, spaCy, LLM local). Os formatos de chaves com prefixo ficam em `src/veu/data/segredos.json`, usado também pelo JavaScript.
- `src/veu/analyzer.py`: junta detectores e resolve sobreposições.
- `src/veu/anonymizer.py` e `vault.py`: operadores, cofre e restauração (inclusive em streaming).
- `src/veu/gateway/`: formatos das APIs de IA (adaptadores e SSE), compartilhados pelo proxy e pelos transportes.
- `src/veu/server/`: proxy Starlette, API REST, playground e painel (`panel.py`, `static/painel.html`, rotas em `_panel_routes` e `run_panel` no `app.py`).
- `src/veu/atalhos.py`: atalhos e início com o computador (Windows, macOS, Linux). `web/instalar.ps1` e `web/instalar.sh`: instaladores de um comando (o `.ps1` precisa continuar só com ASCII).
- `src/veu/integrations/`: transportes httpx/httpx2, atalhos de SDK, LangChain, MCP, decorador, pandas, logging, structlog, loguru e Sentry.
- `src/veu/sessions.py`: cofre compartilhado por várias chamadas (base do decorador, LangChain e MCP).
- `src/veu/files.py`, `documents.py` e `sources.py`: arquivos (CSV, JSON, Word, Excel, PowerPoint, PDF) e fontes (Notion, Google, links).
- `src/veu/reporting.py`: relatórios (texto, GitHub, SARIF, JSON). `src/veu/hooks.py`: ganchos para Claude Code e Cursor. `src/veu/demo.py`: `veu demonstrar`.
- `src/veu/integrations/litellm.py`: guardrail do LiteLLM. `src/veu/server/state.py`: sessões (memória e Redis), auditoria encadeada e métricas.
- `js/`: biblioteca `@guhttps/veu` (TypeScript), com `createFetch` e o middleware do AI SDK. Porte fiel do Python; `scripts/gerar-dados.mjs` copia as listas de `src/veu/data`.
- `web/`: página do GitHub Pages. `extensao/`: extensão para Chrome e Edge. `plugin/` e `.claude-plugin/`: plugin do Claude Code com skill.
- `deploy/`: chart Helm e docker-compose.
- `action.yml`: GitHub Action composta (verifica dados pessoais no repositório).
- `src/veu/bench/`: gerador de dados anotados e avaliação.

## Regras

- Nunca use dados pessoais reais em código, testes, exemplos ou commits. Gere valores com `veu.surrogates`.
- Não ajuste o detector olhando `VALIDATION_TEMPLATES` em `bench/generator.py`: esse conjunto mede a generalização.
- Toda correção de detecção vem com um teste que falharia sem ela.
- Identificadores em inglês; textos para o usuário, chaves do `veu.toml` e comandos da CLI em português do Brasil.
- O núcleo (`veu` sem extras) não pode ganhar dependências. Servidor e integrações usam extras opcionais, importados só dentro do módulo da integração. A biblioteca JavaScript também não tem dependências de execução.
- Nunca escreva chaves de API com formato real em testes ou exemplos: monte os valores em pedaços (`"sk-" + "proj-" + ...`), para os scanners de segredos não confundirem com chaves reais.
- Uma mudança de detecção em Python precisa ir também para `js/src/` (o teste de conformidade falha se as duas versões divergirem).
- Commits em inglês, no imperativo. Registre mudanças visíveis no `CHANGELOG.md`.
