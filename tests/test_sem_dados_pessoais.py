"""Arquivos com dados de quem mantém o projeto nunca entram no repositório nem nos pacotes publicados.

O cache do wrangler (Cloudflare) guarda o e-mail e o id da conta, e arquivos .env guardam segredos. Um deles já entrou
num commit uma vez; estes testes impedem que aconteça de novo.
"""

import subprocess
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def arquivos_no_git() -> list[str]:
    try:
        saida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("fora de um repositório git")
    return saida.splitlines()


def test_cache_do_wrangler_e_env_fora_do_repositorio():
    proibidos = [
        caminho for caminho in arquivos_no_git()
        if "/.wrangler/" in f"/{caminho}" or Path(caminho).name == ".env" or Path(caminho).name.startswith(".env.local")
    ]
    assert proibidos == []


def test_gitignore_cobre_o_cache_do_wrangler():
    linhas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".wrangler/" in linhas


def test_pacote_de_codigo_exclui_caches_e_segredos():
    configuracao = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    excluidos = configuracao["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    for padrao in ("**/.wrangler", "**/.env", "**/node_modules"):
        assert padrao in excluidos
