"""Gera os ícones PNG da extensão (quadrado arredondado com três faixas, como um véu). Sem dependências."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

FUNDO = (35, 78, 82)
FAIXA = (255, 255, 255)
AMOSTRAS = 4  # suavização das bordas


def _dentro(x: float, y: float) -> tuple[bool, bool]:
    """(dentro do quadrado arredondado, dentro de uma faixa) para coordenadas de 0 a 1."""
    raio = 0.22
    cx = min(max(x, raio), 1 - raio)
    cy = min(max(y, raio), 1 - raio)
    fundo = (x - cx) ** 2 + (y - cy) ** 2 <= raio**2
    faixas = ((0.36, 0.76), (0.52, 0.64), (0.68, 0.52))
    faixa = False
    for altura, fim in faixas:
        meia = 0.055
        if abs(y - altura) <= meia and 0.24 - meia <= x <= fim + meia:
            ex = min(max(x, 0.24), fim)
            faixa = faixa or (x - ex) ** 2 + (y - altura) ** 2 <= meia**2
    return fundo, faixa


def icone(tamanho: int) -> bytes:
    linhas = []
    for py in range(tamanho):
        linha = bytearray([0])
        for px in range(tamanho):
            soma = [0.0, 0.0, 0.0, 0.0]
            for sy in range(AMOSTRAS):
                for sx in range(AMOSTRAS):
                    x = (px + (sx + 0.5) / AMOSTRAS) / tamanho
                    y = (py + (sy + 0.5) / AMOSTRAS) / tamanho
                    fundo, faixa = _dentro(x, y)
                    if fundo:
                        cor = FAIXA if faixa else FUNDO
                        for i in range(3):
                            soma[i] += cor[i]
                        soma[3] += 255
            n = AMOSTRAS * AMOSTRAS
            alfa = soma[3] / n
            cor = [round(soma[i] / (soma[3] / 255)) for i in range(3)] if alfa else [0, 0, 0]
            linha += bytes([*cor, round(alfa)])
        linhas.append(bytes(linha))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(b"".join(linhas), 9)) + bloco(b"IEND", b"")


def main() -> None:
    raiz = Path(__file__).resolve().parent.parent
    pasta = raiz / "extensao" / "icones"
    pasta.mkdir(parents=True, exist_ok=True)
    for tamanho in (16, 32, 48, 128):
        (pasta / f"{tamanho}.png").write_bytes(icone(tamanho))
    (raiz / "plugin" / ".claude-plugin" / "icon.png").write_bytes(icone(512))
    # Ícone do Windows (.ico com imagens PNG dentro) para os atalhos criados por "veu atalhos".
    tamanhos = (16, 32, 48, 256)
    imagens = [icone(tamanho) for tamanho in tamanhos]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    deslocamento = 6 + 16 * len(imagens)
    entradas = b""
    for tamanho, imagem in zip(tamanhos, imagens, strict=True):
        lado = 0 if tamanho >= 256 else tamanho
        entradas += struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32, len(imagem), deslocamento)
        deslocamento += len(imagem)
    (raiz / "src" / "veu" / "server" / "static" / "veu.ico").write_bytes(cabecalho + entradas + b"".join(imagens))
    print("ícones da extensão e do plugin gerados")


if __name__ == "__main__":
    main()
