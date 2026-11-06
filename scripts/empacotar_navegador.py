"""Prepara a extensão e a página web com a biblioteca JavaScript já compilada (js/dist/veu.global.js).

    cd js && npm run build && cd ..
    python scripts/empacotar_navegador.py            # copia o veu.global.js e gera dist/veu-extensao-<versão>.zip
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


def main() -> int:
    if not BUNDLE.exists():
        print("Falta js/dist/veu.global.js: rode 'npm run build' na pasta js.", file=sys.stderr)
        return 1
    for target in (EXTENSION, WEB):
        shutil.copyfile(BUNDLE, target / "veu.global.js")
    version = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))["version"]
    output = ROOT / "dist" / f"veu-extensao-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in EXTENSION_FILES:
            archive.write(EXTENSION / name, name)
        for icon in sorted((EXTENSION / "icones").glob("*.png")):
            archive.write(icon, f"icones/{icon.name}")
    print(f"{output.relative_to(ROOT)} e web/veu.global.js prontos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
