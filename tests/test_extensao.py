"""Extensão: padrões seguros e o pacote do Firefox."""

import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extensao"


def test_real_data_in_the_page_is_opt_in():
    """Na página, o código do site também leria os dados reais: a restauração na tela vem desligada."""
    assert re.search(r"restaurarRespostas: false", (EXTENSION / "fundo.js").read_text(encoding="utf-8"))
    assert re.search(r"restaurarRespostas: false", (EXTENSION / "conteudo.js").read_text(encoding="utf-8"))


def test_content_script_runs_before_the_page():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_scripts"][0]["run_at"] == "document_start"


def test_content_script_recognizes_hash_placeholders():
    source = (EXTENSION / "conteudo.js").read_text(encoding="utf-8")
    pattern = re.search(r"const PLACEHOLDER = /(.+)/;", source).group(1).replace("\\\\", "\\")
    assert re.search(pattern, "[CPF_3fa2c1d9e07b4a12]")


def test_firefox_manifest():
    import importlib.util

    spec = importlib.util.spec_from_file_location("empacotar", ROOT / "scripts" / "empacotar_navegador.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    firefox = module.firefox_manifest(manifest)
    assert firefox["background"] == {"scripts": ["fundo.js"]}
    assert firefox["browser_specific_settings"]["gecko"]["id"] == "veu@guhttps.github.io"
    assert "minimum_chrome_version" not in firefox and firefox["version"] == manifest["version"]


def test_zips_when_built(tmp_path):
    dist = ROOT / "dist"
    zips = sorted(dist.glob("veu-extensao-firefox-*.zip")) if dist.exists() else []
    if not zips:
        return  # o pacote só existe depois de scripts/empacotar_navegador.py
    with zipfile.ZipFile(zips[-1]) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert {"manifest.json", "conteudo.js", "fundo.js", "veu.global.js"} <= names
    assert "scripts" in manifest["background"]
