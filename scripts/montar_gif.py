"""Junta os quadros de build/demo-pt ou demo-en (node scripts/gravar_demo.mjs) em docs/demo.gif ou demo-en.gif.

    python scripts/montar_gif.py [--idioma en] [--largura 640]

Precisa do Pillow (pip install pillow). Usa uma paleta só para todos os quadros, para o GIF ficar pequeno e sem
cores piscando.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--largura", type=int, default=640)
    parser.add_argument("--idioma", choices=("pt", "en"), default="pt")
    parser.add_argument("--saida")
    args = parser.parse_args()
    args.saida = args.saida or str(ROOT / "docs" / ("demo.gif" if args.idioma == "pt" else "demo-en.gif"))
    folder = ROOT / "build" / f"demo-{args.idioma}"
    frames = json.loads((folder / "quadros.json").read_text(encoding="utf-8"))
    images = []
    for frame in frames:
        image = Image.open(folder / frame["arquivo"]).convert("RGB")
        height = round(image.height * args.largura / image.width)
        images.append(image.resize((args.largura, height), Image.LANCZOS))
    palette = images[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    quantized = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images]
    quantized[0].save(args.saida, save_all=True, append_images=quantized[1:], duration=[f["ms"] for f in frames],
                      loop=0, optimize=True, disposal=1)
    size = Path(args.saida).stat().st_size
    print(f"{args.saida}: {len(frames)} quadros, {images[0].width}x{images[0].height}, {size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
