# Distribuição

Onde o Véu está publicado e como publicar nos canais que ainda dependem de um passo manual.

| Canal | Situação | Comando para quem instala |
|---|---|---|
| PyPI | Publicado a cada tag `vX.Y.Z` | `pip install veu`, `pipx install veu` ou `uv tool install veu` |
| npm | Publicado a cada tag | `npm install @guhttps/veu` |
| Imagem Docker | Publicada a cada tag | `docker run ghcr.io/guhttps/veu` |
| Instalador de um comando | Na página do Véu | `irm https://guhttps.github.io/veu/instalar.ps1 \| iex` (Windows) ou `curl -LsSf https://guhttps.github.io/veu/instalar.sh \| sh` |
| Homebrew (macOS e Linux) | Fórmula pronta em [`homebrew/veu.rb`](homebrew/veu.rb); falta o tap | `brew install guhttps/veu/veu` |
| Scoop (Windows) | Manifesto pronto em [`scoop/veu.json`](scoop/veu.json); falta o bucket | `scoop bucket add veu https://github.com/guhttps/scoop-veu` e `scoop install veu` |
| winget | Ainda não | — |

## Atualizar os manifestos

Depois de publicar uma versão no PyPI:

```bash
python scripts/atualizar_manifestos.py          # a última versão do PyPI (ou: ... 0.6.0)
```

O script lê os endereços e os hashes do próprio PyPI e reescreve `homebrew/veu.rb` e `scoop/veu.json`.

## Homebrew: criar o tap

1. Crie o repositório público `guhttps/homebrew-veu` no GitHub.
2. Copie `homebrew/veu.rb` para `Formula/veu.rb` nesse repositório.
3. Quem instala roda `brew install guhttps/veu/veu`.

A fórmula instala a roda (wheel) do PyPI num ambiente virtual com o Python do Homebrew. Como o núcleo do Véu não tem dependências, não há nada para compilar. `brew test veu` confere que um CPF sai escondido. Foi testada no Homebrew para Linux; no macOS, o caminho é o mesmo.

## Scoop: criar o bucket

1. Crie o repositório público `guhttps/scoop-veu`.
2. Copie `scoop/veu.json` para `bucket/veu.json`.
3. Quem instala roda `scoop bucket add veu https://github.com/guhttps/scoop-veu` e `scoop install veu`.

O manifesto depende do Python do Scoop, baixa a roda do PyPI conferindo o hash e a instala num ambiente virtual, sem baixar mais nada. `checkver` e `autoupdate` deixam o bucket se atualizar sozinho com o `excavator` do Scoop.

## Por que ainda não no winget

O winget instala programas com instalador próprio (`.exe`, `.msi` ou `.msix`). O Véu é um pacote Python e ainda não tem um executável assinado. Enquanto isso, o instalador de um comando e o Scoop cobrem o Windows. Quando houver um executável assinado (a assinatura gratuita do SignPath para projetos abertos é um caminho), o manifesto do winget passa a fazer sentido.
