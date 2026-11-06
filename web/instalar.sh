#!/bin/sh
# Instalador do Véu para macOS e Linux. Não precisa de sudo nem de Python instalado.
#
# Abra o Terminal e cole:
#     curl -LsSf https://guhttps.github.io/veu/instalar.sh | sh
#
# O que ele faz:
#   1. instala o uv (gerenciador de Python da Astral), se ainda não houver;
#   2. instala o Véu com o painel, o suporte a Excel/Word/PDF e o servidor MCP;
#   3. cria o atalho "Véu" e abre o painel no navegador.
# Para desinstalar: uv tool uninstall veu
set -eu

pacote="${VEU_PACOTE:-veu[servidor,mcp,documentos]}"

echo ""
echo "  Instalando o Véu: proteção de dados para IA"

echo ""
echo "  1 de 3: preparando o Python (uv)..."
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

echo ""
echo "  2 de 3: instalando o Véu (pode levar um minuto)..."
uv tool install --force --python 3.13 "$pacote"
uv tool update-shell >/dev/null 2>&1 || true
veu="$(uv tool dir --bin)/veu"

echo ""
echo "  3 de 3: criando o atalho Véu..."
if [ -z "${VEU_SEM_ATALHO:-}" ]; then
    "$veu" atalhos >/dev/null || true
fi

echo ""
echo "  Pronto! O Véu está instalado."
echo "  Para abrir depois: use o atalho Véu ou digite  veu painel  no Terminal."
echo ""
if [ -z "${VEU_SEM_ABRIR:-}" ]; then
    exec "$veu" painel
fi
