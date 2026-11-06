# Como contribuir

Obrigado pelo interesse! Bugs, ideias, nomes que faltam e casos difíceis para o benchmark são muito bem-vindos.

> [!IMPORTANT]
> **Nunca use dados pessoais reais** em issues, testes ou exemplos. Gere valores falsos com `veu gerar-dataset` ou com as funções de `veu.surrogates`.

## Ambiente

Requer Python 3.11 ou mais recente.

```bash
git clone https://github.com/guhttps/veu && cd veu
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## Antes de abrir um pull request

```bash
pytest                       # testes
ruff check .                 # lint
veu avaliar                  # o vazamento na validação não pode piorar
```

Se mexeu num detector, mude também a versão JavaScript e confira que as duas continuam iguais:

```bash
python scripts/gerar_conformidade.py
cd js && npm ci && npm test
```

Se mexeu na extensão ou na página: `cd js && npm run build && cd .. && python scripts/empacotar_navegador.py && node extensao/teste/e2e.mjs`.

O CI roda:

- os testes no Linux e no Windows, com Python 3.11 a 3.14;
- a versão JavaScript no Node 22, 24 e 26;
- a extensão num Chrome de verdade;
- o chart Helm e o guardrail do LiteLLM.

Ele falha se o vazamento do benchmark passar de 5%.

## Onde mexer

| Quero... | Arquivo |
|---|---|
| Adicionar ou ajustar um documento (formato, contexto, pontuação) | `src/veu/recognizers/patterns.py` (e `js/src/patterns.ts`) |
| Adicionar o formato de chave de um serviço | `src/veu/data/segredos.json` (vale para Python e JavaScript) |
| Senhas e segredos por nome de campo | `src/veu/recognizers/secrets.py` (e `js/src/secrets.ts`) |
| Melhorar a detecção de nomes | `src/veu/recognizers/persons.py` e as listas em `src/veu/data/` |
| Adicionar nomes, sobrenomes, cidades ou empresas | `src/veu/data/*.txt` (um por linha) |
| Melhorar endereços | `src/veu/recognizers/addresses.py` |
| Validar um novo documento | `src/veu/validators.py` (e um gerador em `surrogates.py`) |
| Suportar outra API de IA | `src/veu/gateway/adapters.py` (e um provedor em `config.py`) |
| Integrar com uma biblioteca (LangChain, Sentry, pandas...) | `src/veu/integrations/` |
| Ferramentas do servidor MCP | `src/veu/integrations/mcp.py` |
| Arquivos de dados e relatórios (SARIF, GitHub) | `src/veu/files.py` e `src/veu/reporting.py` |
| Word, Excel, PowerPoint e PDF | `src/veu/documents.py` |
| Notion, Google e links | `src/veu/sources.py` |
| Biblioteca JavaScript, `createFetch`, AI SDK | `js/src/` |
| Extensão, página web e plugin do Claude Code | `extensao/`, `web/`, `plugin/` |
| Gateway para empresas, Helm e LiteLLM | `src/veu/server/`, `deploy/`, `src/veu/integrations/litellm.py` |
| Mudar o proxy ou a API REST | `src/veu/server/app.py` |
| Adicionar casos ao benchmark | `src/veu/bench/hard.py` (escritos à mão) ou `generator.py` |

## Regras do benchmark

- Casos difíceis novos vão para `bench/hard.py`.
- **Não ajuste o detector olhando o conjunto de validação** (`VALIDATION_TEMPLATES`). Se precisar de mais modelos para ajustar, acrescente ao conjunto de desenvolvimento. Assim o número da validação continua honesto.
- Toda correção de detecção vem com um teste que falharia sem ela.

## Convenções

- Código e identificadores em inglês; textos para quem usa (mensagens, documentação, chaves do `veu.toml`, comandos da CLI) em português do Brasil.
- Mensagens de commit em inglês, no imperativo: `Add`, `Fix`, `Detect`...
- Registre mudanças visíveis no `CHANGELOG.md`, na seção `[Unreleased]`.

## Publicar uma versão (mantenedores)

1. Atualize a versão em todos estes lugares (o teste `test_plugin_files_are_consistent` confere os três primeiros):
   - `__version__` em `src/veu/__init__.py`;
   - `plugin/.claude-plugin/plugin.json` e `.claude-plugin/marketplace.json`;
   - `js/package.json` e `VERSION` em `js/src/index.ts`;
   - `extensao/manifest.json`;
   - `deploy/helm/veu/Chart.yaml`.
2. No `CHANGELOG.md`, renomeie `[Unreleased]` para `[X.Y.Z] - AAAA-MM-DD`.
3. Crie a tag `vX.Y.Z` e envie. O workflow de release:
   - publica a release no GitHub, com o pacote Python, o pacote npm e o `.zip` da extensão;
   - publica a imagem em `ghcr.io/guhttps/veu`;
   - publica no PyPI e no npm, se as variáveis `PYPI_PUBLICAR` e `NPM_PUBLICAR` estiverem ligadas.
