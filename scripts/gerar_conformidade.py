"""Gera js/test/conformidade.json: o que o Véu em Python detecta e produz para uma lista de textos.

O teste da versão JavaScript exige exatamente o mesmo resultado, para as duas não divergirem.
Rode depois de mudar um detector:  python scripts/gerar_conformidade.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from veu import Veu  # noqa: E402
from veu.bench.generator import generate  # noqa: E402
from veu.bench.hard import hard_samples  # noqa: E402

EXTRA = [
    "Oi, aqui é a Maria das Graças Souza, CPF 529.982.247-25, moro na Rua das Flores, 123.",
    "falei com joao da silva ontem, ele pediu o boleto",
    "Prezado Sr. Ferreira, seu processo 0001234-55.2023.8.26.0100 foi atualizado.",
    "CNPJ 12.ABC.345/01DE-35 e CNPJ 11.222.333/0001-81",
    "Pix: 123e4567-e89b-12d3-a456-426614174000 e IP 192.168.0.10, IPv6 2001:db8::1",
    "Nascida em 12 de março de 1990, RG 12.345.678-9 SSP/SP, CNH 02650306461",
    "placa ABC1D23 e RENAVAM 00639884962, cartão 4111 1111 1111 1111",
    "IBAN DE89 3704 0044 0532 0130 00 e telefone +1 415 555 2671",
    "Senha: deve conter 8 caracteres. password = getpass() e DB_PASSWORD=hunter2!",
    "postgres://admin:S3nh4Forte@db.interna.example:5432/app.",
    "Av. Paulista, 1578, apto 42, bloco B, São Paulo",
    "Encontro na Praça da Sé às 10h com a Dra. Ana Lúcia",
    "O Banco do Brasil e a Construtora Horizonte Ltda assinaram com João Pereira",
    "Março foi bom para o Marco e para a Rosa.",
]


def main() -> None:
    veu = Veu()
    texts = EXTRA + [sample.text for sample in generate(200, seed=11)] + [sample.text for sample in hard_samples()]
    cases = []
    for text in dict.fromkeys(texts):
        if any(ord(char) > 0xFFFF for char in text):
            continue  # posições em UTF-16 (JavaScript) e em pontos de código (Python) seriam diferentes
        entities = veu.analyze(text)
        cases.append({
            "texto": text,
            "entidades": [[e.label, e.start, e.end, e.score] for e in entities],
            "anonimizado": veu.anonymize(text).text,
            "mascarado": veu.with_operator("mascara").anonymize(text).text,
        })
    target = ROOT / "js" / "test" / "conformidade.json"
    target.write_text(json.dumps({"casos": cases}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{target.relative_to(ROOT)}: {len(cases)} casos")


if __name__ == "__main__":
    main()
