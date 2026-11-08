"""Prepara a extensão e a página web com a biblioteca JavaScript já compilada (js/dist/veu.global.js).

    cd js && npm run build && cd ..
    python scripts/empacotar_navegador.py            # copia o veu.global.js e gera dist/veu-extensao-<versão>.zip

Gera também dist/veu-extensao-firefox-<versão>.zip, com o manifesto que o Firefox espera (background.scripts e
browser_specific_settings). O Edge usa o mesmo pacote do Chrome.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "js" / "dist" / "veu.global.js"
EXTENSION = ROOT / "extensao"
WEB = ROOT / "web"
EXTENSION_FILES = ("manifest.json", "politica.json", "fundo.js", "conteudo.js", "popup.html", "popup.css", "popup.js",
                   "veu.global.js")


FIREFOX_ID = "veu@guhttps.github.io"


def firefox_manifest(manifest: dict) -> dict:
    """Manifesto para o Firefox: página de fundo em vez de service worker e o identificador do complemento."""
    result = {key: value for key, value in manifest.items() if key != "minimum_chrome_version"}
    result["background"] = {"scripts": [manifest["background"]["service_worker"]]}
    result["browser_specific_settings"] = {"gecko": {"id": FIREFOX_ID, "strict_min_version": "128.0"}}
    return result


def write_zip(output: Path, manifest: dict) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for name in EXTENSION_FILES:
            if name != "manifest.json":
                archive.write(EXTENSION / name, name)
        for icon in sorted((EXTENSION / "icones").glob("*.png")):
            archive.write(icon, f"icones/{icon.name}")


def main() -> int:
    if not BUNDLE.exists():
        print("Falta js/dist/veu.global.js: rode 'npm run build' na pasta js.", file=sys.stderr)
        return 1
    for target in (EXTENSION, WEB):
        shutil.copyfile(BUNDLE, target / "veu.global.js")
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    output = ROOT / "dist" / f"veu-extensao-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    write_zip(output, manifest)
    firefox = ROOT / "dist" / f"veu-extensao-firefox-{version}.zip"
    write_zip(firefox, firefox_manifest(manifest))
    print(f"{output.relative_to(ROOT)}, {firefox.relative_to(ROOT)} e web/veu.global.js prontos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
