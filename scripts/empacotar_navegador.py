"""Prepara a extensão e a página web com a biblioteca JavaScript já compilada (js/dist/veu.global.js).

    cd js && npm run build && cd ..
    python scripts/empacotar_navegador.py            # copia o veu.global.js e gera dist/veu-extensao-<versão>.zip

Gera também dist/veu-extensao-firefox-<versão>.zip, com o manifesto que o Firefox espera (background.scripts e
browser_specific_settings). O Edge usa o mesmo pacote do Chrome.
"""

from __future__ import annotations

import base64
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "js" / "dist" / "veu.global.js"
EXTENSION = ROOT / "extensao"
WEB = ROOT / "web"
EXTENSION_FILES = ("manifest.json", "politica.json", "licenca.js", "fundo.js", "conteudo.js", "popup.html", "popup.css",
                   "popup.js", "veu.global.js", "pagina.css", "relatorio.html", "relatorio.js", "arquivos.html",
                   "arquivos.js", "pdf.min.mjs", "pdf.worker.min.mjs", "pdfjs-LICENSE.txt", "imagens.js", "leitor.html", "leitor.js")
# pdf.js (Mozilla, Apache-2.0) lê o texto dos PDFs na página de arquivos do Véu Pro. Vem sem mudanças do npm.
PDFJS = ROOT / "js" / "node_modules" / "pdfjs-dist"
# Imagens (Véu Pro): o Tesseract lê o texto dos prints e o jsQR acha os QR Codes, tudo no navegador. Vêm sem
# mudanças do npm para a pasta ocr/ da extensão e do site (português, modo LSTM: ~5,7 MB).
NODE = ROOT / "js" / "node_modules"
OCR_FILES = {
    "tesseract.min.js": NODE / "tesseract.js" / "dist" / "tesseract.min.js",
    "worker.min.js": NODE / "tesseract.js" / "dist" / "worker.min.js",
    "tesseract-core-simd-lstm.wasm.js": NODE / "tesseract.js-core" / "tesseract-core-simd-lstm.wasm.js",
    "por.traineddata.gz": NODE / "@tesseract.js-data" / "por" / "4.0.0_best_int" / "por.traineddata.gz",
    "jsQR.js": NODE / "jsqr" / "dist" / "jsQR.js",
    "tesseract.js-LICENSE.md": NODE / "tesseract.js" / "LICENSE.md",
    "tesseract.js-core-LICENSE.txt": NODE / "tesseract.js-core" / "LICENSE",
    "jsQR-LICENSE.txt": NODE / "jsqr" / "LICENSE",
    "face-api.js": NODE / "@vladmandic" / "face-api" / "dist" / "face-api.js",
    "face-api-LICENSE.txt": NODE / "@vladmandic" / "face-api" / "LICENSE",
}
# Modelo do detector de rostos (TinyFaceDetector, ~190 KB): vai num script, não por fetch, porque a página do site
# bloqueia conexões. rostos-modelo.js define veuModeloRostos = { manifesto, pesos (base64) }.
FACE_MODEL = NODE / "@vladmandic" / "face-api" / "model"
GENERATED_OCR_FILES = ("rostos-modelo.js", "LEIA-ME.txt")
OCR_NOTICE = """Leitor de imagens do Véu Pro (tudo roda no navegador; a imagem não sai do computador)

tesseract.min.js, worker.min.js: tesseract.js 7.0.0 (Apache-2.0), https://github.com/naptha/tesseract.js
tesseract-core-simd-lstm.wasm.js: tesseract.js-core 6.1.2 (Apache-2.0), com o Tesseract OCR (Apache-2.0) e o
  Leptonica (BSD-2-Clause), https://github.com/naptha/tesseract.js-core
por.traineddata.gz: dados de português do tessdata_best_int (Apache-2.0), via @tesseract.js-data/por 1.0.0 (MIT)
jsQR.js: jsQR 1.4.0 (Apache-2.0), https://github.com/cozmo/jsQR
face-api.js: @vladmandic/face-api 1.7.15 (MIT), com o TensorFlow.js (Apache-2.0), https://github.com/vladmandic/face-api
rostos-modelo.js: o modelo TinyFaceDetector do mesmo pacote (tiny_face_detector_model), em base64

Todos sem mudanças, copiados do npm por scripts/empacotar_navegador.py.
"""


FIREFOX_ID = "veu@guhttps.github.io"
FIREFOX_PRO_DATA = ("authenticationInfo", "personallyIdentifyingInfo")


def firefox_manifest(manifest: dict) -> dict:
    """Manifesto para o Firefox: página de fundo em vez de service worker e o identificador do complemento."""
    result = {key: value for key, value in manifest.items() if key != "minimum_chrome_version"}
    # No Chrome, o service worker carrega licenca.js com importScripts; no Firefox, a página de fundo lista os
    # arquivos. Ela também lê as imagens do Véu Pro (tem DOM e workers), então leva o leitor e não usa offscreen.
    result["background"] = {"scripts": ["veu.global.js", "licenca.js", "imagens.js", "leitor.js",
                                        manifest["background"]["service_worker"]]}
    result["permissions"] = [item for item in manifest["permissions"] if item != "offscreen"]
    # A Mozilla exige que extensões novas declarem os dados que enviam (o Firefox mostra isso ao instalar). Sem o
    # Véu Pro, nada sai; com ele, a renovação manda a própria chave (um token com o e-mail da assinatura), e o
    # popup pede essa permissão opcional ao ativar a chave. A chave existe a partir do Firefox 140.
    result["browser_specific_settings"] = {"gecko": {
        "id": FIREFOX_ID, "strict_min_version": "140.0", "data_collection_permissions": {
            "required": ["none"], "optional": list(FIREFOX_PRO_DATA)},
    }}
    return result


def write_zip(output: Path, manifest: dict) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for name in EXTENSION_FILES:
            if name != "manifest.json":
                archive.write(EXTENSION / name, name)
        for name in sorted(OCR_FILES) + list(GENERATED_OCR_FILES):
            archive.write(EXTENSION / "ocr" / name, f"ocr/{name}")
        for icon in sorted((EXTENSION / "icones").glob("*.png")):
            archive.write(icon, f"icones/{icon.name}")
        # Nome e descrição em cada idioma: as lojas mostram uma página por idioma do pacote.
        for messages in sorted((EXTENSION / "_locales").glob("*/messages.json")):
            archive.write(messages, f"_locales/{messages.parent.name}/messages.json")


def main() -> int:
    if not BUNDLE.exists():
        print("Falta js/dist/veu.global.js: rode 'npm run build' na pasta js.", file=sys.stderr)
        return 1
    for target in (EXTENSION, WEB):
        shutil.copyfile(BUNDLE, target / "veu.global.js")
    if not (PDFJS / "build" / "pdf.min.mjs").exists():
        print("Falta o pdf.js: rode 'npm ci' na pasta js.", file=sys.stderr)
        return 1
    # A página web também lê PDFs (arquivos inteiros) e confere a chave do Véu Pro com o mesmo licenca.js da extensão.
    for target in (EXTENSION, WEB):
        for name in ("pdf.min.mjs", "pdf.worker.min.mjs"):
            shutil.copyfile(PDFJS / "build" / name, target / name)
        shutil.copyfile(PDFJS / "LICENSE", target / "pdfjs-LICENSE.txt")
    shutil.copyfile(EXTENSION / "licenca.js", WEB / "licenca.js")
    # Imagens: o mesmo imagens.js e a mesma pasta ocr/ na extensão e no site.
    needed = [*OCR_FILES.values(), FACE_MODEL / "tiny_face_detector_model-weights_manifest.json",
              FACE_MODEL / "tiny_face_detector_model.bin"]
    missing = [str(source.relative_to(ROOT)) for source in needed if not source.exists()]
    if missing:
        print(f"Falta o leitor de imagens ({', '.join(missing)}): rode 'npm ci' na pasta js.", file=sys.stderr)
        return 1
    shutil.copyfile(EXTENSION / "imagens.js", WEB / "imagens.js")
    manifesto = json.loads((FACE_MODEL / "tiny_face_detector_model-weights_manifest.json").read_text(encoding="utf-8"))
    pesos = base64.b64encode((FACE_MODEL / "tiny_face_detector_model.bin").read_bytes()).decode("ascii")
    modelo = ("// Gerado por scripts/empacotar_navegador.py: o modelo TinyFaceDetector do @vladmandic/face-api (MIT).\n"
              f"globalThis.veuModeloRostos = {{ manifesto: {json.dumps(manifesto)}, pesos: \"{pesos}\" }};\n")
    for target in (EXTENSION, WEB):
        (target / "ocr").mkdir(exist_ok=True)
        for name, source in OCR_FILES.items():
            shutil.copyfile(source, target / "ocr" / name)
        (target / "ocr" / "LEIA-ME.txt").write_text(OCR_NOTICE, encoding="utf-8")
        (target / "ocr" / "rostos-modelo.js").write_text(modelo, encoding="utf-8")
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    output = ROOT / "dist" / f"veu-extensao-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    write_zip(output, manifest)
    firefox = ROOT / "dist" / f"veu-extensao-firefox-{version}.zip"
    write_zip(firefox, firefox_manifest(manifest))
    print(f"{output.relative_to(ROOT)}, {firefox.relative_to(ROOT)} e a página web (web/) prontos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
