"""Gera os manifestos do Homebrew e do Scoop para uma versão do Véu publicada no PyPI.

    python scripts/atualizar_manifestos.py            # a última versão do PyPI
    python scripts/atualizar_manifestos.py 0.6.0

Os endereços e os hashes vêm do PyPI (o JSON da versão), sem baixar nada. Os arquivos ficam em packaging/;
depois, copie-os para o tap e o bucket (veja packaging/README.md).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTION = "Esconde dados pessoais e segredos antes de o texto chegar à IA"
HOMEPAGE = "https://github.com/guhttps/veu"

FORMULA = '''class Veu < Formula
  include Language::Python::Virtualenv

  desc "{description}"
  homepage "{homepage}"
  url "{sdist_url}"
  sha256 "{sdist_sha256}"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "{wheel_url}"
    sha256 "{wheel_sha256}"
  end

  def install
    venv = virtualenv_create(libexec, "python3.13")
    venv.pip_install_and_link resource("veu-wheel")
  end

  test do
    output = pipe_output("#{{bin}}/veu anonimizar", "CPF 529.982.247-25")
    assert_match "[CPF_1]", output
    refute_match "529.982.247-25", output
  end
end
'''


def release(version: str | None) -> dict:
    url = f"https://pypi.org/pypi/veu/{version}/json" if version else "https://pypi.org/pypi/veu/json"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - endereço fixo do PyPI
        return json.load(response)


def files(data: dict) -> dict[str, dict]:
    found = {}
    for item in data["urls"]:
        if item["packagetype"] == "sdist":
            found["sdist"] = item
        elif item["filename"].endswith("-py3-none-any.whl"):
            found["wheel"] = item
    if set(found) != {"sdist", "wheel"}:
        raise SystemExit("O PyPI não tem o código-fonte e a roda dessa versão.")
    return found


def scoop_manifest(version: str, wheel: dict) -> dict:
    name = wheel["filename"]
    return {
        "version": version,
        "description": DESCRIPTION + ".",
        "homepage": HOMEPAGE,
        "license": "MIT",
        "depends": "python",
        # "#/nome.whl" guarda o arquivo como está: o Scoop não abre a roda, e o pip a instala sem internet.
        "url": f"{wheel['url']}#/{name}",
        "hash": wheel["digests"]["sha256"],
        "installer": {"script": [
            'python -m venv "$dir\\venv"',
            '& "$dir\\venv\\Scripts\\python.exe" -m pip install --no-index --no-deps --disable-pip-version-check '
            '"$dir\\veu-$version-py3-none-any.whl"',
        ]},
        "bin": "venv\\Scripts\\veu.exe",
        "checkver": {"url": "https://pypi.org/pypi/veu/json", "jsonpath": "$.info.version"},
        "autoupdate": {"url": "https://files.pythonhosted.org/packages/py3/v/veu/veu-$version-py3-none-any.whl"
                              "#/veu-$version-py3-none-any.whl"},
    }


def main(argv: list[str]) -> int:
    data = release(argv[0] if argv else None)
    version = data["info"]["version"]
    found = files(data)
    homebrew = ROOT / "packaging" / "homebrew" / "veu.rb"
    scoop = ROOT / "packaging" / "scoop" / "veu.json"
    homebrew.parent.mkdir(parents=True, exist_ok=True)
    scoop.parent.mkdir(parents=True, exist_ok=True)
    homebrew.write_text(FORMULA.format(
        description=DESCRIPTION, homepage=HOMEPAGE,
        sdist_url=found["sdist"]["url"], sdist_sha256=found["sdist"]["digests"]["sha256"],
        wheel_url=found["wheel"]["url"], wheel_sha256=found["wheel"]["digests"]["sha256"],
    ), encoding="utf-8", newline="\n")
    scoop.write_text(json.dumps(scoop_manifest(version, found["wheel"]), ensure_ascii=False, indent=4) + "\n",
                     encoding="utf-8", newline="\n")
    print(f"Manifestos da versão {version}: {homebrew.relative_to(ROOT)} e {scoop.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
