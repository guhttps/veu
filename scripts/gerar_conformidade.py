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
    "O servidor 192.168.0.10 atende na porta 5432; acesse 10.0.0.5:8080 ou [2001:db8::1]:443.",
    "ssh -p 2222 root@203.0.113.7 e docker run -p 8080:80 nginx; depois abra http://203.0.113.7:3000/admin.",
    "Banco em db.interna:5432, cache em cache.prod.local, API em https://api.empresa.example:8443/v1 e localhost:3000.",
    'PORT=8080, DB_PORT=5432 e {"host": "fila.corp", "port": 6379}. O servidor fila.empresa.example:5672 responde.',
    "Não são portas: reunião às 10:30, app.py:120, apartamento 302, relatório 2024, versão 1.2.3:45, porta 65536, "
    "nota 8080, db.interna.example e joao@empresa.local.",
    # Achados da simulação de uso (scripts/simular_usuarios.py).
    "Comprovante de transferência Pix\nDe: Altair Batista Linhares\nPara: Thiago Lima\nChave Pix: (82) 98501-3510",
    "Nome:\nMaria Souza\nForma Pagamento: Boleto",
    "Resetei a senha para Tmp#4821xQ. Depois troquei a senha pra Mudar@2026; a senha do wifi fica casa2026.",
    "Preciso de uma senha para acessar o sistema e esqueci a senha para entrar no portal.",
    "Advogada (OAB/SP 123.456), Dra. Ana Lima (CRM-SC 34636), CRM/MG: 54.321, CREA-SP 5061234567, CRP 06/123456. "
    "Não são registros: Dynamics CRM 365, OAB 2024, a série 3 da escola.",
    "CTPS: 3492025 série 0533-SP; carteira de trabalho nº 1234567, SÉRIE 00012.",
    "Login gislaine.vieira, pasta /home/joao_silva/docs, ssh humberto.maciel@10.0.0.5. Não são logins: "
    "maria.souza.com.br, config.yaml, nota.fiscal, rosa.silva.",
    "Login admin, senha bGsEDD$34. Rede Empresa_Visitantes, senha F73rbT@27. Não são senhas: senha inválida, "
    "senha 123456, senha alterada com sucesso.",
    "Cookie: session_id=d8a3d4d8bd11e4f65709e86bed6dfd05; theme=dark\nSet-Cookie: PHPSESSID=9a8b7c6d5e4f3a2b1c0d; path=/",
    "INSERT INTO clientes (id, nome, nascimento) VALUES\n(1021, 'Ana Lima', '1985-04-03'),\n(1022, 'Rui Costa', "
    "'1990-12-01');\nSELECT * FROM pedidos WHERE criado_em > '2026-01-01';\nnome;nascimento\nAna Lima;03/04/1985",
    "MAC 95:7F:76:CE:A3:DA e 1c-bb-bd-4a-58-ad; ether aabb.ccdd.eeff. Não são: FF:FF:FF:FF:FF:FF, 10:30, "
    "cisco aabb.ccdd.eeff.",
    "Local do sinistro (app): -19.376349, -47.473154. Coordenadas 12.3456, 45.6789. Não é: média 12.3456, 45.6789.",
    "Prontuário: 2412179 e RA 2024631292, carteirinha 91483354148818137, apólice nº 334553733535. Não são: "
    "matrícula feita em 12/03/2024 e apólice com prêmio de R$ 1.234,56.",
    "Checkout: https://loja.example/checkout?email=olga.costa%40example.org&cpf=52998224725&cupom=BLACK10",
    "<dest><xNome>Ana Lima</xNome><enderDest><xLgr>Avenida Moisés Martins</xLgr><nro>120</nro></enderDest></dest> Batida traseira na Av. Paulista.",
    "Data of birth: born 1985-04-03; DOB 03/04/1985; birth date 1985-04-03.",
    # Achados da simulação de ataques (scripts/simular_ataques.py): disfarces.
    "CPF 529-982-247-25, CPF 5 2 9 9 8 2 2 4 7 2 5 e a sequência 5 2 9 9 8 2 2 4 7 2 5 do sorteio.",
    "e-mail mаria.souza@example.com e cliente Маria Souza.",
    "CPF ٥٢٩.٩٨٢.٢٤٧-٢٥ e CPF ५२९.९८२.२४७-२५.",
    # Tipos novos: carteira cripto, 2FA, Wi-Fi, links com token, OTP, CVV, Pix, boleto, certidão, RNM, IMEI, GPS.
    "minha seed: abandon ability able about above absent absorb abstract absurd abuse access accident",
    "1. legal 2. winner 3. thank 4. year 5. wave 6. sausage 7. worth 8. useful 9. legal 10. winner 11. thank 12. yellow",
    "Lista: about above across act action actor actual add address adult advance advice after again against age",
    "Redefinir: https://app.example.com/reset?token=8f3a9c2b7d1e4f6a9b0c3d5e7f1a2b4c&u=2 e "
    "otpauth://totp/Empresa:joao?secret=JBSWY3DPEHPK3PXP&issuer=Empresa",
    "WIFI:T:WPA;S:CasaSouza;P:minhaSenha2024!;; Seu código de verificação é 483920. OTP: 1234.",
    "cartão final 4242, validade 12/27, CVV 123; código de segurança do cartão: 9876",
    "Pix: 00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal"
    "6008BRASILIA62070503***63041D3D",
    "Linha digitável: 34191.79001 01043.510047 91020.150008 1 96610000017500; inválida: "
    "34191.79001 01043.510048 91020.150008 1 96610000017500",
    "Matrícula da certidão: 104539 01 55 2013 1 00012 021 0000123 55. RNM V123456-7.",
    "IMEI do aparelho: 35-209900-176148-1; cartão 352099001761481; localização 23°33'01\"S 46°38'02\"W",
    "joao.silva [at] gmail [dot] com, maria arroba empresa ponto com ponto br e te vejo at home dot",
    "X-Amz-Signature=3f2c1a9e8b7d4e6f9a0b1c2d3e4f5a6b7c8d9e0f&X-Amz-Credential=abc",
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
