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

O CI roda os testes no Linux e no Windows, com Python 3.11 a 3.14, e falha se o vazamento do benchmark passar de 5%.

## Onde mexer

| Quero... | Arquivo |
|---|---|
| Adicionar ou ajustar um documento (formato, contexto, pontuação) | `src/veu/recognizers/patterns.py` |
| Melhorar a detecção de nomes | `src/veu/recognizers/persons.py` e as listas em `src/veu/data/` |
| Adicionar nomes, sobrenomes, cidades ou empresas | `src/veu/data/*.txt` (um por linha) |
| Melhorar endereços | `src/veu/recognizers/addresses.py` |
| Validar um novo documento | `src/veu/validators.py` (e um gerador em `surrogates.py`) |
| Suportar outra API de IA | `src/veu/gateway/adapters.py` |
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

1. Atualize `__version__` em `src/veu/__init__.py`.
2. No `CHANGELOG.md`, renomeie `[Unreleased]` para `[X.Y.Z] - AAAA-MM-DD`.
3. Crie a tag `vX.Y.Z` e envie. O workflow de release gera o pacote e publica a release no GitHub.
