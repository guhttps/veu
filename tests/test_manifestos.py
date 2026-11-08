"""Manifestos do Homebrew e do Scoop gerados a partir do JSON do PyPI (sem rede: dados de exemplo)."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("atualizar_manifestos", ROOT / "scripts" / "atualizar_manifestos.py")
manifests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifests)

PYPI = {"info": {"version": "9.9.9"}, "urls": [
    {"packagetype": "sdist", "filename": "veu-9.9.9.tar.gz", "url": "https://files.example/veu-9.9.9.tar.gz",
     "digests": {"sha256": "a" * 64}},
    {"packagetype": "bdist_wheel", "filename": "veu-9.9.9-py3-none-any.whl",
     "url": "https://files.example/veu-9.9.9-py3-none-any.whl", "digests": {"sha256": "b" * 64}},
]}


def test_generates_both_manifests(monkeypatch, tmp_path):
    monkeypatch.setattr(manifests, "ROOT", tmp_path)
    monkeypatch.setattr(manifests, "release", lambda version: PYPI)
    assert manifests.main(["9.9.9"]) == 0
    formula = (tmp_path / "packaging" / "homebrew" / "veu.rb").read_text(encoding="utf-8")
    assert 'url "https://files.example/veu-9.9.9.tar.gz"' in formula and f'sha256 "{"a" * 64}"' in formula
    assert 'url "https://files.example/veu-9.9.9-py3-none-any.whl"' in formula and f'sha256 "{"b" * 64}"' in formula
    assert '"#{bin}/veu anonimizar"' in formula  # a interpolação do Ruby sobrevive ao format do Python
    scoop = json.loads((tmp_path / "packaging" / "scoop" / "veu.json").read_text(encoding="utf-8"))
    assert scoop["version"] == "9.9.9" and scoop["hash"] == "b" * 64
    assert scoop["url"].endswith("#/veu-9.9.9-py3-none-any.whl")  # o Scoop guarda a roda sem abrir
    assert "$version" in scoop["installer"]["script"][1]          # o autoupdate não fica preso à versão antiga
    assert scoop["autoupdate"]["url"].endswith("veu-$version-py3-none-any.whl#/veu-$version-py3-none-any.whl")


def test_needs_sdist_and_wheel():
    with pytest.raises(SystemExit):
        manifests.files({"urls": [PYPI["urls"][0]]})


def test_committed_manifests_match_the_generator():
    formula = (ROOT / "packaging" / "homebrew" / "veu.rb").read_text(encoding="utf-8")
    scoop = json.loads((ROOT / "packaging" / "scoop" / "veu.json").read_text(encoding="utf-8"))
    version = scoop["version"]
    assert f"veu-{version}.tar.gz" in formula and f"veu-{version}-py3-none-any.whl" in formula
    assert "pip_install_and_link" in formula and scoop["bin"] == "venv\\Scripts\\veu.exe"
