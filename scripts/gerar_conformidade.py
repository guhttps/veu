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
from veu.bench.desafio import challenge_samples  # noqa: E402
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
    "CPF: 529.982.***-** e ***.982.247-**; CNPJ 11.222.333/****-** e 11 222 333 0001 81",
    "RG nº 12.34***-*, CNH nº 02650******, Título de Eleitor nº 1023****0191, CEP 01310 100",
    "RG 12 345 678 9 e CNH 0265030646-1; o campo ***.***.***-** veio vazio",
    "Oi, sou a Rayane Souza. kkkk a rayane esqueceu o carregador. RAYANE SOUZA assinou. A rayanesouza não.",
    "Responsável: Anthony Raul Viana. Endereço: Avenida Paulista. Evento em São Cristóvão, com Kawanny Rodrigues.",
    "O José Carlos ligou; depois o jose voltou. Rosa Pereira ligou e a rosa murchou. Razão Social: Exemplo Ltda",
    "CPF 529.982.247‑25, CPF ５２９.９８２.２４７-２５ e e-mail maria­.souza@example.com",
    "tel (11) 98765‑4321; chave sk-​proj-Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d; período 2020–2021",
    "NIF: 123 456 789. Cartão de Cidadão 12345678 9 ZZ1. NISS 11234567892. CUIT 20-12345678-6 e cuit 30123456781.",
    "DNI 12.345.678, CURP XAXX900101HDFXXX03, RFC PEPJ900101AB8 e o genérico XAXX010101000.",
    "RUT 12.345.678-5, RUT: 211234560019, cédula 1.234.567-2, cédula 1712345675, NIT 900.123.456-8.",
    "RUC 20123456786, RUC 1234567-9, RIF V-12345678-1, RG 12.345.678-5 e protocolo 202569473616.",
    "Ana Costa ligou; a Costa disse que mora na costa. Data de nascimento de Enrico Nascimento: 01/02/1990.",
    "Nascida em 7 de setembro de 1985, CEP 01310-100, tel (11) 98765-4321, +44 20 7946 0958, IP 192.0.2.44 e 2001:db8:85a3::8a2e:370:7334.",
    "NUIT 123 456 785, BI 123456789LA123, BI nº 123456789012A e o NUIT 123 456 784.",
    "SSN 123-45-6789, ITIN 900-70-1234, ssn: 123456789, inválido 000-12-3456, Medicare MBI 1EG4-TE5-MK73.",
    "DNI 12345678Z, NIE X1234567L, errado 12345678A e C.F. RSSMRA80A01H501U.",
    "NIR 1 80 01 75 123 456 60, NIR 180012A12345620 e Steuer-ID 12345678911.",
    "NINO AB 12 34 56 C, ni number AB123456, NHS number 999 000 0018 e BSN 111222333.",
    "SIN 123 456 782, Aadhaar 2345 6789 0124, PAN ABCPD1234E e sin 123 456 781.",
    "Passaporte:\nP<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10",
    "VIN 1M8GDM9AXKP042788, chassi 9BWZZZ377VT004251 e série 11111111111111111.",
    "carteira 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed, btc 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa, "
    "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq e o falso 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb.",
    "Sem contexto: o pedido 123456782, o código ABCPD1234E, o lote 1M8GDM9AXKP042789, o protocolo 180017512345660, "
    "o certificado com notAfter 261108123045Z e a nota 20231108A.",
]


def main() -> None:
    veu = Veu()
    texts = EXTRA + [sample.text for sample in generate(200, seed=11)] + [sample.text for sample in hard_samples()]
    texts += [sample.text for sample in challenge_samples()]  # só para conferir que as duas versões dão o mesmo
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
            "generalizado": veu.with_operator("generalizar").anonymize(text).text,
        })
    target = ROOT / "js" / "test" / "conformidade.json"
    target.write_text(json.dumps({"casos": cases}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{target.relative_to(ROOT)}: {len(cases)} casos")


if __name__ == "__main__":
    main()
