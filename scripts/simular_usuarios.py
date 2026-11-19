"""Simulação de uso: pessoas de várias profissões usando o Véu no dia a dia, sempre com dados fictícios.

    python scripts/simular_usuarios.py                 # relatório no terminal
    python scripts/simular_usuarios.py --rodadas 5     # mais variações de cada cenário
    python scripts/simular_usuarios.py --semente 7     # outra sorte de dados
    python scripts/simular_usuarios.py --sem-js        # só a versão Python

Cada cenário é um texto como as pessoas escrevem de verdade (WhatsApp, planilha, log, e-mail, contrato), com os
dados gerados por veu.surrogates. A simulação confere:

- vazamento: um dado pessoal que devia sumir e continuou no texto;
- exagero: um trecho comum (valor, artigo de lei, versão, código de pedido) que foi escondido;
- volta: a resposta da IA, escrita com os marcadores, volta com os dados reais;
- JavaScript: a biblioteca da extensão e da página dá o mesmo resultado que a Python.

Os cenários não fazem parte da validação nem do desafio do benchmark; servem para achar falhas de uso real.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from veu import Veu  # noqa: E402
from veu import surrogates as s  # noqa: E402
from veu import validators as v  # noqa: E402
from veu.vault import RestorePolicy  # noqa: E402

# --- Geradores de valores que veu.surrogates não tem ------------------------------------------------------------


def _sorteia(rng: random.Random, gerar, valido) -> str:
    while True:
        valor = gerar()
        if valido(valor):
            return valor


def nif_pt(rng: random.Random) -> str:
    return _sorteia(rng, lambda: rng.choice("123") + "".join(rng.choice("0123456789") for _ in range(8)),
                    v.is_valid_nif_pt)


def cuit(rng: random.Random) -> str:
    def gerar():
        corpo = rng.choice(("20", "23", "27")) + "".join(rng.choice("0123456789") for _ in range(9))
        return f"{corpo[:2]}-{corpo[2:10]}-{corpo[10]}"
    return _sorteia(rng, gerar, v.is_valid_cuit)


def rut_cl(rng: random.Random) -> str:
    def gerar():
        numero = rng.randint(5_000_000, 25_000_000)
        digito = rng.choice("0123456789K")
        return f"{numero:,}".replace(",", ".") + f"-{digito}"
    return _sorteia(rng, gerar, v.is_valid_rut_cl)


def vin(rng: random.Random) -> str:
    letras = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return _sorteia(rng, lambda: "9BW" + "".join(rng.choice(letras) for _ in range(14)), v.is_valid_vin)


def chave(prefixo: str, rng: random.Random, tamanho: int = 40) -> str:
    # Montada em pedaços, para os scanners de segredos não confundirem com uma chave de verdade.
    return prefixo + "".join(rng.choice("abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789")
                             for _ in range(tamanho))


def _alnum(rng: random.Random, tamanho: int, letras: str = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") -> str:
    return "".join(rng.choice(letras) for _ in range(tamanho))


_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def ssn(rng: random.Random) -> str:
    return _sorteia(rng, lambda: f"{rng.randint(1, 899):03d}-{rng.randint(1, 99):02d}-{rng.randint(1, 9999):04d}",
                    v.is_valid_ssn)


def dni_es(rng: random.Random) -> str:
    numero = rng.randint(10_000_000, 99_999_999)
    return f"{numero}{'TRWAGMYFPDXBNJZSQVHLCKE'[numero % 23]}"


def nino(rng: random.Random) -> str:
    return _sorteia(rng, lambda: _alnum(rng, 2, "ABCEGHJKLMNPRSTWXYZ") + _alnum(rng, 6, "0123456789")
                    + rng.choice("ABCD"), v.is_valid_nino)


def codice_fiscale(rng: random.Random) -> str:
    def gerar():
        return (_alnum(rng, 6, "BCDFGHLMNPRSTVZ") + f"{rng.randint(40, 99)}" + rng.choice("ABCDEHLMPRST")
                + f"{rng.randint(1, 28):02d}" + rng.choice("ABCDEFGHILM") + f"{rng.randint(100, 999)}"
                + rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    return _sorteia(rng, gerar, v.is_valid_codice_fiscale)


def aadhaar(rng: random.Random) -> str:
    def gerar():
        d = str(rng.randint(2, 9)) + _alnum(rng, 11, "0123456789")
        return f"{d[:4]} {d[4:8]} {d[8:]}"
    return _sorteia(rng, gerar, v.is_valid_aadhaar)


def _luhn_ok(numero: str) -> bool:
    soma = 0
    for i, digito in enumerate(reversed(numero)):
        n = int(digito) * (2 if i % 2 else 1)
        soma += n - 9 if n > 9 else n
    return soma % 10 == 0


def imei(rng: random.Random) -> str:
    return _sorteia(rng, lambda: "35" + _alnum(rng, 13, "0123456789"), _luhn_ok)


def ssh_privada(rng: random.Random) -> str:
    # Montada em pedaços, para os scanners de segredos não confundirem com uma chave de verdade.
    linhas = ["".join(rng.choice(_B64) for _ in range(70)) for _ in range(4)]
    return "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + "\n".join(linhas) + "\n-----END OPENSSH " + "PRIVATE KEY-----"


def jwt(rng: random.Random) -> str:
    url = _B64.replace("+", "-").replace("/", "_")
    return ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "eyJ" + "".join(rng.choice(url) for _ in range(60)) + "."
            + "".join(rng.choice(url) for _ in range(43)))


def host_interno(rng: random.Random) -> str:
    return f"{rng.choice(('db', 'srv', 'app', 'erp', 'fs'))}{rng.randint(1, 9):02d}.{rng.choice(('corp', 'local', 'internal', 'lan'))}"


# --- Cenários ---------------------------------------------------------------------------------------------------

# Cada campo: (rótulo esperado ou None, gerador). O rótulo é só informativo; o vazamento é medido pelo texto.
# Campos marcados com "?" no rótulo são desejáveis, não obrigatórios (aparecem como "sugestão" no relatório).


@dataclass
class Cenario:
    perfil: str
    texto: str
    campos: dict[str, tuple[str | None, object]]
    manter: list[str] = field(default_factory=list)
    resposta: str = "Pronto. Revisei o texto de <<primeiro_marcador>> e está tudo certo."


def _nome(rng, palavras=None):
    return s.fake_name(rng, palavras or rng.choice((2, 3)))


def _primeiro(rng):
    return rng.choice(s.first_names())


CENARIOS: list[Cenario] = [
    Cenario(
        "Advogada: petição inicial",
        "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA 3ª VARA CÍVEL DA COMARCA DE CAMPINAS\n\n"
        "Processo nº <<processo>>\n\n<<nome>>, brasileira, casada, professora, portadora do RG nº <<rg>> e inscrita "
        "no CPF sob o nº <<cpf>>, residente e domiciliada na <<endereco>>, CEP <<cep>>, vem, por sua advogada "
        "(OAB/SP <<oab>>), com fundamento no art. 5º, inciso X, da Constituição Federal e na Lei 13.709/2018, "
        "propor a presente AÇÃO DE INDENIZAÇÃO em face de TELEFONIA EXEMPLO S.A., inscrita no CNPJ sob o nº "
        "<<cnpj>>. Valor da causa: R$ 15.000,00.\n\nMelhore a redação dos fatos.",
        {"processo": ("PROCESSO", s.fake_processo), "nome": ("PESSOA", _nome), "rg": ("RG", s.fake_rg),
         "cpf": ("CPF", s.fake_cpf), "endereco": ("ENDERECO", s.fake_address), "cep": ("CEP", s.fake_cep),
         "oab": ("REGISTRO?", lambda rng: f"{rng.randint(100, 499)}.{rng.randint(100, 999)}"),
         "cnpj": ("CNPJ", s.fake_cnpj)},
        manter=["art. 5º", "Lei 13.709/2018", "R$ 15.000,00", "3ª VARA CÍVEL"],
    ),
    Cenario(
        "Contador: planilha de clientes",
        "razao_social;cnpj;responsavel;email;telefone;faturamento\n"
        "Padaria Exemplo Ltda;<<cnpj>>;<<nome>>;<<email>>;<<tel>>;R$ 48.320,15\n"
        "Oficina Modelo ME;<<cnpj2>>;<<nome2>>;<<email2>>;<<tel2>>;R$ 12.900,00\n\n"
        "Confira se o Simples Nacional ainda vale para os dois clientes acima em 2026.",
        {"cnpj": ("CNPJ", s.fake_cnpj), "nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email),
         "tel": ("TELEFONE", s.fake_phone), "cnpj2": ("CNPJ", lambda rng: s.fake_cnpj(rng, formatted=False)),
         "nome2": ("PESSOA", _nome), "email2": ("EMAIL", s.fake_email),
         "tel2": ("TELEFONE", lambda rng: s.fake_phone(rng, "espacos"))},
        manter=["R$ 48.320,15", "R$ 12.900,00", "Simples Nacional", "2026"],
    ),
    Cenario(
        "Médica: encaminhamento",
        "Resumo para encaminhamento\nPaciente: <<nome>>\nData de nascimento: <<nasc>>\nCartão SUS: <<cns>>\n"
        "Telefone: <<tel>>\nQueixa: ansiedade há 6 meses, CID F41.1. Em uso de sertralina 50mg 1x ao dia. "
        "PA 120/80 mmHg.\nMédica responsável: Dra. <<nome2>> (CRM-SC <<crm>>)\n\n"
        "Escreva uma carta de encaminhamento para o psiquiatra.",
        {"nome": ("PESSOA", _nome), "nasc": ("DATA_NASCIMENTO", s.fake_birthdate), "cns": ("CNS", s.fake_cns),
         "tel": ("TELEFONE", s.fake_phone), "nome2": ("PESSOA", _nome),
         "crm": ("REGISTRO?", lambda rng: str(rng.randint(10000, 39999)))},
        manter=["CID F41.1", "50mg", "120/80"],
    ),
    Cenario(
        "RH: admissão",
        "Admissão de colaborador\nNome: <<nome>>\nCPF: <<cpf>>\nPIS: <<pis>>\nCTPS: <<ctps>> série <<serie>>\n"
        "Nascimento: <<nasc>>\nEndereço: <<endereco>> - CEP <<cep>>\nBanco Exemplo, agência 1234, conta corrente "
        "<<conta>>\nChave Pix: <<email>>\nSalário: R$ 4.200,00\n\nMonte o e-mail de boas-vindas para segunda-feira.",
        {"nome": ("PESSOA", _nome), "cpf": ("CPF", s.fake_cpf), "pis": ("PIS", s.fake_pis),
         "ctps": ("CTPS?", lambda rng: str(rng.randint(1_000_000, 9_999_999))),
         "serie": ("CTPS?", lambda rng: f"{rng.randint(1, 999):04d}-SP"),
         "nasc": ("DATA_NASCIMENTO", s.fake_birthdate), "endereco": ("ENDERECO", s.fake_address),
         "cep": ("CEP", s.fake_cep), "conta": ("CONTA_BANCARIA", s.fake_account), "email": ("EMAIL", s.fake_email)},
        manter=["R$ 4.200,00"],
    ),
    Cenario(
        "Cliente no WhatsApp: tudo minúsculo",
        "oi boa tarde, meu nome é <<nome>>, comprei um fone no site e nao chegou ainda. meu cpf é <<cpf>> e o "
        "pedido é o 48213. pode me chamar no zap <<tel>> ou no email <<email>>. obrigada",
        {"nome": ("PESSOA", lambda rng: _nome(rng).lower()), "cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)),
         "tel": ("TELEFONE", lambda rng: s.fake_phone(rng, "puro")), "email": ("EMAIL", s.fake_email)},
        manter=["48213"],
    ),
    Cenario(
        "Equipe no WhatsApp: nomes curtos",
        "[14:02] <<p1>>: gente, o <<p2>> vai cobrir meu plantão sábado\n[14:03] <<p2>>: fechado, me passa o "
        "endereço do cliente\n[14:05] <<p1>>: <<endereco>>, apto 302, falar com a dona <<nome>>, tel <<tel>>",
        {"p1": ("PESSOA", _primeiro), "p2": ("PESSOA", _primeiro), "endereco": ("ENDERECO", s.fake_address),
         "nome": ("PESSOA", _nome), "tel": ("TELEFONE", s.fake_phone)},
        manter=["[14:02]", "plantão sábado"],
    ),
    Cenario(
        "Programador: deploy quebrado",
        "Meu deploy quebrou, segue o log:\n\nTraceback (most recent call last):\n  File \"/app/main.py\", line 42, "
        "in conectar\n    conn = psycopg2.connect(os.environ[\"DATABASE_URL\"])\npsycopg2.OperationalError: could "
        "not connect to server at \"<<host>>\" (<<ip>>), port 5432 failed\n\nMeu .env:\n"
        "DATABASE_URL=postgres://app:<<senha>>@<<host>>:5432/vendas\nOPENAI_API_KEY=<<openai>>\n"
        "STRIPE_SECRET_KEY=<<stripe>>\nADMIN_EMAIL=<<email>>\n\nO que está errado?",
        {"host": ("SERVIDOR", host_interno), "ip": ("IP", s.fake_ipv4),
         "senha": ("SENHA", lambda rng: chave("Pg", rng, 14)),
         "openai": ("CHAVE_API", lambda rng: chave("sk-" + "proj-", rng, 48)),
         "stripe": ("CHAVE_API", lambda rng: chave("sk_" + "live_", rng, 24)), "email": ("EMAIL", s.fake_email)},
        manter=["/app/main.py", "line 42", "psycopg2.OperationalError"],
    ),
    Cenario(
        "Suporte de redes: log do servidor",
        "Analise esse log e diga se é ataque:\n<<ip>> - - [18/Nov/2026:10:15:32 -0300] \"GET /wp-login.php "
        "HTTP/1.1\" 404 162 \"-\" \"Mozilla/5.0\"\n<<ip2>> - - [18/Nov/2026:10:15:33 -0300] \"POST /api/login "
        "HTTP/1.1\" 401 52 \"-\" \"curl/8.4.0\"\nO servidor é o <<host>>, porta 8443.",
        {"ip": ("IP", s.fake_ipv4), "ip2": ("IP", s.fake_ipv4), "host": ("SERVIDOR", host_interno)},
        manter=["/wp-login.php", "HTTP/1.1", "curl/8.4.0", "404"],
    ),
    Cenario(
        "Suporte de TI: chamado",
        "Chamado #20931 - usuário <<nome>> (login <<login>>) não consegue acessar a VPN. Resetei a senha para "
        "<<senha>>. Máquina <<host>>, IP <<ip>>, ramal 4021. Escreva a resposta explicando como trocar a senha.",
        {"nome": ("PESSOA", _nome), "login": ("USUARIO?", lambda rng: s.fold(_nome(rng, 2)).lower().replace(" ", ".")),
         "senha": ("SENHA", lambda rng: chave("Tmp#", rng, 8)), "host": ("SERVIDOR", host_interno),
         "ip": ("IP", s.fake_ipv4)},
        manter=["#20931", "VPN", "ramal 4021"],
    ),
    Cenario(
        "Vendedor: e-mail com assinatura",
        "Olá <<p1>>, tudo bem?\n\nConforme conversamos, segue a proposta. O valor fica em R$ 3.990,00 por mês, com "
        "10% de desconto no plano anual.\n\nAbraços,\n<<nome>>\nExecutivo de Contas | Empresa Exemplo\n<<tel>> | "
        "<<email>>\n\nDeixe esse e-mail mais curto.",
        {"p1": ("PESSOA", _primeiro), "nome": ("PESSOA", _nome),
         "tel": ("TELEFONE", lambda rng: s.fake_phone(rng, "internacional")), "email": ("EMAIL", s.fake_email)},
        manter=["R$ 3.990,00", "10%", "Executivo de Contas"],
    ),
    Cenario(
        "Professora: notas da turma",
        "Notas da turma 3ºB (prova de matemática):\n<<nome>> - 7,5\n<<nome2>> - 4,0\n<<nome3>> - 9,0\n"
        "<<nome4>> - 5,5\n\nQuais alunos precisam de recuperação (nota menor que 6)? Escreva um recado para os pais.",
        {"nome": ("PESSOA", _nome), "nome2": ("PESSOA", _nome), "nome3": ("PESSOA", _nome),
         "nome4": ("PESSOA", _nome)},
        manter=["3ºB", "7,5", "menor que 6"],
    ),
    Cenario(
        "Imobiliária: contrato de aluguel",
        "CONTRATO DE LOCAÇÃO RESIDENCIAL\nLOCADOR: <<nome>>, brasileiro, divorciado, engenheiro, RG <<rg>> SSP/SP, "
        "CPF <<cpf>>.\nLOCATÁRIA: <<nome2>>, brasileira, solteira, analista, CPF <<cpf2>>, telefone <<tel>>.\n"
        "IMÓVEL: <<endereco>>, apartamento 42, CEP <<cep>>, com vaga para o veículo placa <<placa>>.\n"
        "ALUGUEL: R$ 2.300,00 mensais, reajustado pelo IGP-M.\n\nAponte riscos para o locador.",
        {"nome": ("PESSOA", _nome), "rg": ("RG", s.fake_rg), "cpf": ("CPF", s.fake_cpf), "nome2": ("PESSOA", _nome),
         "cpf2": ("CPF", s.fake_cpf), "tel": ("TELEFONE", s.fake_phone), "endereco": ("ENDERECO", s.fake_address),
         "cep": ("CEP", s.fake_cep), "placa": ("PLACA", s.fake_plate)},
        manter=["R$ 2.300,00", "IGP-M", "SSP/SP"],
    ),
    Cenario(
        "Financeiro: comprovante Pix",
        "Comprovante de transferência Pix\nValor: R$ 850,00\nData: 18/11/2026 09:41\nDe: <<nome>>\nPara: <<nome2>>\n"
        "Chave Pix: <<tel>>\nInstituição: Banco Exemplo S.A.\nID da transação: E00000000202611180941abc12345\n\n"
        "Escreva um recibo desse pagamento.",
        {"nome": ("PESSOA", _nome), "nome2": ("PESSOA", _nome), "tel": ("TELEFONE", s.fake_phone)},
        manter=["R$ 850,00", "18/11/2026 09:41"],
    ),
    Cenario(
        "Oficina: sinistro",
        "Sinistro 2026/0457: veículo placa <<placa>>, RENAVAM <<renavam>>, chassi <<vin>>, condutor <<nome>> "
        "(CNH <<cnh>>), telefone <<tel>>. Batida traseira na Av. Paulista. Orçamento: R$ 6.780,00. "
        "Redija o relato para a seguradora.",
        {"placa": ("PLACA", s.fake_plate), "renavam": ("RENAVAM", s.fake_renavam), "vin": ("VIN", vin),
         "nome": ("PESSOA", _nome), "cnh": ("CNH", s.fake_cnh), "tel": ("TELEFONE", s.fake_phone)},
        manter=["2026/0457", "R$ 6.780,00", "Av. Paulista"],
    ),
    Cenario(
        "Cliente de Portugal",
        "Bom dia, sou o <<nome>>, contribuinte n.º <<nif>>, moro na Rua das Flores, 123, 4050-262 Porto. O meu "
        "telemóvel é +351 9<<tel_pt>>. Preciso de uma reclamação formal para a operadora.",
        {"nome": ("PESSOA", _nome), "nif": ("NIF_PT", nif_pt),
         "tel_pt": ("TELEFONE", lambda rng: f"{rng.randint(1, 6)}{rng.randint(0, 9)} {rng.randint(100, 999)} "
                    f"{rng.randint(100, 999)}")},
        manter=["Porto"],
    ),
    Cenario(
        "Cliente da Argentina",
        "Hola, soy <<nome>>, mi CUIT es <<cuit>>. Vivo en Av. Corrientes 1234, CABA. Mi celular es +54 9 11 "
        "<<cel>>. Necesito una carta para el banco.",
        {"nome": ("PESSOA", _nome), "cuit": ("CUIT", cuit),
         "cel": ("TELEFONE", lambda rng: f"{rng.randint(2000, 6999)}-{rng.randint(1000, 9999)}")},
        manter=["CABA"],
    ),
    Cenario(
        "Cliente do Chile",
        "Hola, mi nombre es <<nome>> y mi RUT es <<rut>>. Necesito redactar un reclamo por un cobro duplicado de "
        "$45.990 en mi tarjeta.",
        {"nome": ("PESSOA", _nome), "rut": ("RUT", rut_cl)},
        manter=["$45.990"],
    ),
    Cenario(
        "Estudante: entrevista do TCC",
        "Transcrição da entrevista 3 (TCC):\nEntrevistadora: Qual sua idade e onde trabalha?\n<<p1>>: Tenho 34 anos, "
        "sou enfermeira em Joinville, trabalho lá desde 2015.\nEntrevistadora: E seu e-mail para contato?\n"
        "<<p1>>: <<email>>\n\nResuma as respostas da entrevistada.",
        {"p1": ("PESSOA", _primeiro), "email": ("EMAIL", s.fake_email)},
        manter=["34 anos", "2015"],
    ),
    Cenario(
        "Marketing: leads em JSON",
        '[{"nome": "<<nome>>", "email": "<<email>>", "telefone": "<<tel>>", "cidade": "Curitiba", "origem": '
        '"Instagram"}, {"nome": "<<nome2>>", "email": "<<email2>>", "telefone": "<<tel2>>", "cidade": "Recife", '
        '"origem": "Google"}]\n\nSepare esses leads por origem.',
        {"nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email), "tel": ("TELEFONE", s.fake_phone),
         "nome2": ("PESSOA", _nome), "email2": ("EMAIL", s.fake_email),
         "tel2": ("TELEFONE", lambda rng: s.fake_phone(rng, "puro"))},
        manter=["Curitiba", "Instagram", "Recife"],
    ),
    Cenario(
        "Síndica: lista de moradores",
        "Lista de moradores - Bloco B\nApto 101 - <<nome>> - <<tel>> - carro <<placa>>\nApto 102 - <<nome2>> - "
        "<<tel2>>\nApto 103 - <<nome3>> - <<tel3>> - moto <<placa2>>\n\nOrganize em ordem alfabética.",
        {"nome": ("PESSOA", _nome), "tel": ("TELEFONE", s.fake_phone), "placa": ("PLACA", s.fake_plate),
         "nome2": ("PESSOA", _nome), "tel2": ("TELEFONE", s.fake_phone), "nome3": ("PESSOA", _nome),
         "tel3": ("TELEFONE", s.fake_phone), "placa2": ("PLACA", lambda rng: s.fake_plate(rng, mercosul=False))},
        manter=["Bloco B", "Apto 101"],
    ),
    Cenario(
        "Programador: git e ssh",
        "[user]\n\tname = <<nome>>\n\temail = <<email>>\n\n$ ssh deploy@<<ip>> -p 2222\nPermission denied "
        "(publickey).\n\nPor que o push falha?",
        {"nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email), "ip": ("IP", s.fake_ipv4)},
        manter=["Permission denied", "publickey"],
    ),
    Cenario(
        "Recepção da clínica: agendamento",
        "Agendado: Sra. <<nome>> dia 20/11 às 14h, dentista Dr. <<p2>>, retorno. Contato (whats) <<tel>>. "
        "Convênio Unimed, carteirinha <<carteira>>. Mande a confirmação para a paciente.",
        {"nome": ("PESSOA", _nome), "p2": ("PESSOA", _primeiro), "tel": ("TELEFONE", s.fake_phone),
         "carteira": ("CADASTRO", lambda rng: "".join(rng.choice("0123456789") for _ in range(17)))},
        manter=["20/11 às 14h", "Unimed"],
    ),
    Cenario(
        "Loja online: cobrança com cartão",
        "O cliente <<nome>> pagou com o cartão <<cartao>>, validade 08/29, e a compra de R$ 349,90 foi recusada. "
        "Escreva uma mensagem educada pedindo outra forma de pagamento.",
        {"nome": ("PESSOA", _nome), "cartao": ("CARTAO_CREDITO", s.fake_card)},
        manter=["R$ 349,90", "08/29"],
    ),
]


# --- Execução ---------------------------------------------------------------------------------------------------


def _senha(rng):
    return chave("", rng, 6) + rng.choice("@#!$") + str(rng.randint(10, 99))


def _b64(rng, tamanho):
    return "".join(rng.choice(_B64) for _ in range(tamanho))


def _login(rng):
    return s.fold(_nome(rng, 2)).lower().replace(" ", ".")


def _nasc_iso(rng):
    return s.fake_birthdate(rng, "iso")


def _nasc_extenso(rng):
    return s.fake_birthdate(rng, "extenso")


def _maiusculo(rng):
    return _nome(rng).upper()


# Técnicos lidando com acessos, e mais tipos de dados (rodada 3 da simulação).
CENARIOS += [
    Cenario(
        "Nuvem: credenciais da AWS",
        "Configurei o CLI mas dá AccessDenied. Meu ~/.aws/credentials:\n[default]\naws_access_key_id = <<akid>>\n"
        "aws_secret_access_key = <<segredo>>\nregion = sa-east-1\n\nO usuário IAM é <<login>>.",
        {"akid": ("CHAVE_API", lambda rng: "AK" + "IA" + _alnum(rng, 16)), "segredo": ("SEGREDO", lambda rng: _b64(rng, 40)),
         "login": ("PESSOA", _login)},
        manter=["sa-east-1", "AccessDenied"],
    ),
    Cenario(
        "Kubernetes: segredo",
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-credenciais\ndata:\n  username: YWRtaW4=\n"
        "  password: <<senha>>\n---\nO pod fica em CrashLoopBackOff, por quê?",
        {"senha": ("SENHA", lambda rng: _b64(rng, 24))},
        manter=["CrashLoopBackOff", "db-credenciais"],
    ),
    Cenario(
        "Docker: compose com senhas",
        "services:\n  db:\n    image: postgres:16\n    environment:\n      POSTGRES_USER: app\n      POSTGRES_PASSWORD: "
        "<<pg>>\n  api:\n    environment:\n      - JWT_SECRET=<<jwtsecret>>\n      - SMTP_PASS=<<smtp>>\n\n"
        "Por que a api não conecta no banco?",
        {"pg": ("SENHA", _senha), "jwtsecret": ("SEGREDO", lambda rng: _b64(rng, 32)), "smtp": ("SENHA", _senha)},
        manter=["postgres:16", "POSTGRES_USER: app"],
    ),
    Cenario(
        "Redes: VPN WireGuard",
        "[Interface]\nPrivateKey = <<privada>>\nAddress = 10.8.0.2/24\n\n[Peer]\nPublicKey = <<publica>>\nEndpoint = "
        "<<ip>>:51820\nAllowedIPs = 0.0.0.0/0\n\nA VPN conecta mas não navega.",
        {"privada": ("SEGREDO", lambda rng: _b64(rng, 43) + "="), "publica": (None, lambda rng: _b64(rng, 43) + "="),  # chave pública: não é segredo
         "ip": ("IP", s.fake_ipv4)},
        manter=["AllowedIPs"],
    ),
    Cenario(
        "API: requisição HTTP",
        "POST /v1/clientes HTTP/1.1\nHost: api.empresa.example\nAuthorization: Bearer <<jwt>>\nCookie: session_id=<<sessao>>; "
        "theme=dark\nContent-Type: application/json\n\n{\"nome\": \"<<nome>>\", \"cpf\": \"<<cpf>>\", \"nascimento\": "
        "\"<<nasc>>\"}\n\nA API devolve 422, o que falta no corpo?",
        {"jwt": ("TOKEN", jwt), "sessao": ("SEGREDO", lambda rng: _alnum(rng, 32, "abcdef0123456789")),
         "nome": ("PESSOA", _nome), "cpf": ("CPF", s.fake_cpf), "nasc": ("DATA_NASCIMENTO", _nasc_iso)},
        manter=["422", "theme=dark"],
    ),
    Cenario(
        "Suporte: senha na URL do painel",
        "Não consigo abrir https://admin:<<senha>>@painel.<<host>>/dashboard no Chrome, dá erro de certificado.",
        {"senha": ("SENHA", _senha), "host": ("SERVIDOR", host_interno)},
        manter=["erro de certificado"],
    ),
    Cenario(
        "Deploy: chave SSH colada",
        "Meu deploy pede a chave, colei aqui:\n<<chave>>\nComo transformo em formato PEM?",
        {"chave": ("CHAVE_PRIVADA", ssh_privada)},
        manter=["formato PEM"],
    ),
    Cenario(
        "CI: tokens no log",
        "Run npm publish\nnpm notice Publishing to https://registry.npmjs.org/\nnpm error 403 Forbidden\n"
        "env: GITHUB_TOKEN=<<ghp>> NPM_TOKEN=<<npm>>\nO que está errado?",
        {"ghp": ("TOKEN", lambda rng: "gh" + "p_" + _alnum(rng, 36, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
         "npm": ("TOKEN", lambda rng: "np" + "m_" + _alnum(rng, 36, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))},
        manter=["403 Forbidden", "registry.npmjs.org"],
    ),
    Cenario(
        "Monitoramento: webhook do Slack",
        "O alerta do Grafana não chega no Slack. Webhook: https://hooks.slack.com/services/<<t>>/<<b>>/<<x>>",
        {"t": ("SEGREDO?", lambda rng: "T" + _alnum(rng, 8)), "b": ("SEGREDO?", lambda rng: "B" + _alnum(rng, 8)),
         "x": ("SEGREDO", lambda rng: _alnum(rng, 24, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))},
        manter=["Grafana"],
    ),
    Cenario(
        "Infra: inventário de rede",
        "hostname;ip;mac;responsavel\n<<host>>;<<ip>>;<<mac>>;<<nome>>\n<<host2>>;<<ip2>>;<<mac2>>;<<nome2>>\n\n"
        "Quais máquinas estão sem dono?",
        {"host": ("SERVIDOR", host_interno), "ip": ("IP", s.fake_ipv4), "mac": ("MAC", lambda rng: ":".join(
            _alnum(rng, 2, "0123456789ABCDEF") for _ in range(6))), "nome": ("PESSOA", _nome),
         "host2": ("SERVIDOR", host_interno), "ip2": ("IP", s.fake_ipv4), "mac2": ("MAC", lambda rng: "-".join(
             _alnum(rng, 2, "0123456789abcdef") for _ in range(6))), "nome2": ("PESSOA", _nome)},
        manter=["hostname;ip;mac;responsavel"],
    ),
    Cenario(
        "Infra: firewall",
        "iptables -A INPUT -s <<ip>> -p tcp --dport 3306 -j ACCEPT\niptables -A INPUT -s 10.20.0.0/16 -j DROP\n"
        "O MySQL do <<host>> não aceita conexão do servidor de relatórios.",
        {"ip": ("IP", s.fake_ipv4), "host": ("SERVIDOR", host_interno)},
        manter=["-j ACCEPT", "MySQL"],
    ),
    Cenario(
        "Infra: Active Directory",
        "PS> Get-ADUser -Identity <<login>> -Properties *\nDistinguishedName : CN=<<nome>>,OU=Financeiro,DC=empresa,"
        "DC=local\nEmailAddress      : <<email>>\nLastLogonDate     : 17/11/2026 08:12\n\nPor que a conta está bloqueada?",
        {"login": ("PESSOA", _login), "nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email)},
        manter=["OU=Financeiro", "17/11/2026 08:12"],
    ),
    Cenario(
        "Segurança: cabeçalhos de e-mail",
        "From: <<nome>> <<<email>>>\nTo: suporte@empresa.example\nReceived: from <<host>> (<<ip>>) by mx.empresa.example\n"
        "Subject: Fatura em atraso\n\nEsse e-mail é phishing?",
        {"nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email), "host": ("SERVIDOR", host_interno),
         "ip": ("IP", s.fake_ipv4)},
        manter=["Fatura em atraso"],
    ),
    Cenario(
        "Segurança: relatório de pentest",
        "Achado 3 (crítico): credenciais padrão no <<host>> (<<ip>>:8080). Login admin, senha <<senha>>. Também "
        "encontramos a planilha clientes.xlsx com o CPF <<cpf>> de <<nome>>.\n\nReescreva para o relatório executivo.",
        {"host": ("SERVIDOR", host_interno), "ip": ("IP", s.fake_ipv4), "senha": ("SENHA", _senha),
         "cpf": ("CPF", s.fake_cpf), "nome": ("PESSOA", _nome)},
        manter=["Achado 3", "clientes.xlsx"],
    ),
    Cenario(
        "Recepção: senha do Wi-Fi",
        "Wi-Fi para visitantes: rede Empresa_Visitantes, senha <<senha>>. Escreva um aviso para colar na recepção.",
        {"senha": ("SENHA", _senha)},
        manter=["Empresa_Visitantes"],
    ),
    Cenario(
        "Banco de dados: dump SQL",
        "INSERT INTO clientes (id, nome, cpf, email, telefone, nascimento) VALUES\n(1021, '<<nome>>', '<<cpf>>', "
        "'<<email>>', '<<tel>>', '<<nasc>>'),\n(1022, '<<nome2>>', '<<cpf2>>', '<<email2>>', '<<tel2>>', '<<nasc2>>');\n\n"
        "Otimize essa carga para 1 milhão de linhas.",
        {"nome": ("PESSOA", _nome), "cpf": ("CPF", s.fake_cpf), "email": ("EMAIL", s.fake_email),
         "tel": ("TELEFONE", s.fake_phone), "nasc": ("DATA_NASCIMENTO", _nasc_iso), "nome2": ("PESSOA", _nome),
         "cpf2": ("CPF", lambda rng: s.fake_cpf(rng, False)), "email2": ("EMAIL", s.fake_email),
         "tel2": ("TELEFONE", lambda rng: s.fake_phone(rng, "puro")), "nasc2": ("DATA_NASCIMENTO", _nasc_iso)},
        manter=["1021", "1 milhão"],
    ),
    Cenario(
        "Banco de dados: consulta lenta",
        "SELECT * FROM pedidos WHERE cpf_cliente = '<<cpf>>' AND email = '<<email>>' AND criado_em > '2026-01-01';\n"
        "Por que está lenta?",
        {"cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)), "email": ("EMAIL", s.fake_email)},
        manter=["2026-01-01", "SELECT * FROM pedidos"],
    ),
    Cenario(
        "Finanças pessoais: extrato",
        "Extrato - Ag 1234 C/C <<conta>>\n15/11 PIX RECEBIDO <<nome>> 1.200,00\n16/11 PIX ENVIADO chave <<evp>> 350,00\n"
        "17/11 TED <<nome2>> CPF <<cpf>> 2.000,00\n\nClassifique os gastos.",
        {"conta": ("CONTA_BANCARIA", s.fake_account), "nome": ("PESSOA", _maiusculo),
         "evp": ("CHAVE_PIX", s.fake_pix_key), "nome2": ("PESSOA", _maiusculo), "cpf": ("CPF", s.fake_cpf)},
        manter=["1.200,00", "350,00"],
    ),
    Cenario(
        "Laboratório: exame",
        "Paciente: <<nome>>   Prontuário: <<prontuario>>\nNome da mãe: <<mae>>\nNascida em <<nasc>>\n"
        "Hemoglobina glicada: 6,8%   Glicose em jejum: 132 mg/dL\n\nExplique o resultado em linguagem simples.",
        {"nome": ("PESSOA", _nome), "prontuario": ("CADASTRO", lambda rng: str(rng.randint(100000, 9999999))),
         "mae": ("PESSOA", _nome), "nasc": ("DATA_NASCIMENTO", _nasc_extenso)},
        manter=["6,8%", "132 mg/dL"],
    ),
    Cenario(
        "Universidade: aluno",
        "Aluno: <<nome>> - RA <<ra>> - Curso: Engenharia Civil - 7º período\nE-mail institucional: <<email>>\n\n"
        "Escreva um ofício sobre a colação de grau.",
        {"nome": ("PESSOA", _nome), "ra": ("CADASTRO", lambda rng: f"20{rng.randint(10, 26)}{rng.randint(100000, 999999)}"),
         "email": ("EMAIL", lambda rng: s.fake_email(rng, domain="aluno.empresa.example"))},
        manter=["Engenharia Civil", "7º período"],
    ),
    Cenario(
        "Seguradora: apólice",
        "Segurado: <<nome>>, apólice nº <<apolice>>, CPF <<cpf>>, placa <<placa>>. Local do sinistro (app): "
        "<<lat>>, <<lon>>.\nRedija a notificação.",
        {"nome": ("PESSOA", _nome), "apolice": ("CADASTRO", lambda rng: f"{rng.randint(10**11, 10**12 - 1)}"),
         "cpf": ("CPF", s.fake_cpf), "placa": ("PLACA", s.fake_plate),
         "lat": ("COORDENADAS", lambda rng: f"-{rng.uniform(5, 30):.6f}"), "lon": ("COORDENADAS", lambda rng: f"-{rng.uniform(35, 60):.6f}")},
    ),
    Cenario(
        "Celular roubado: IMEI",
        "Meu celular foi roubado, o IMEI é <<imei>> e o número era <<tel>>. Como bloqueio?",
        {"imei": ("IMEI?", imei), "tel": ("TELEFONE", s.fake_phone)},
    ),
    Cenario(
        "Cliente: e-mail disfarçado",
        "me manda no <<usuario>> (arroba) example (ponto) com ou no zap <<tel>>",
        {"usuario": ("EMAIL?", lambda rng: _login(rng)), "tel": ("TELEFONE", s.fake_phone)},
    ),
    Cenario(
        "Cartório: certidão",
        "Certidão de nascimento: <<nome>>, nascido em <<nasc>>, filho de <<mae>> e de <<pai>>.",
        {"nome": ("PESSOA", _nome), "nasc": ("DATA_NASCIMENTO", _nasc_extenso), "mae": ("PESSOA", _nome),
         "pai": ("PESSOA", _nome)},
    ),
    Cenario(
        "Cliente dos EUA",
        "Hi, I'm <<nome>>, my SSN is <<ssn>> and my phone is <<tel>>. I need a letter for my bank.",
        {"nome": ("PESSOA", _nome), "ssn": ("SSN", ssn),
         "tel": ("TELEFONE", lambda rng: f"+1 415 555 01{rng.randint(10, 99)}")},
    ),
    Cenario(
        "RH internacional: documentos",
        "Funcionários estrangeiros: DNI <<dni>>, codice fiscale <<cf>>, NINO <<nino>>, Aadhaar <<aadhaar>>. Confira se "
        "os documentos estão no formato certo.",
        {"dni": ("DNI_ES", dni_es), "cf": ("CODICE_FISCALE", codice_fiscale), "nino": ("NINO", nino),
         "aadhaar": ("AADHAAR", aadhaar)},
    ),
    Cenario(
        "Freelancer: IBAN e cripto",
        "Para pagar o freelancer: IBAN <<iban>> ou a carteira bitcoin <<btc>>.",
        {"iban": ("IBAN", lambda rng: s.fake_iban(rng, "DE", 22)),
         "btc": ("CRIPTO", lambda rng: "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")},
    ),
]


def _cpf_espacos(rng):
    return s.fake_cpf(rng, False)[:3] + " " + s.fake_cpf(rng, False)[3:]


def _cpf_espacado(rng):
    puro = s.fake_cpf(rng, False)
    return f"{puro[:3]} {puro[3:6]} {puro[6:9]} {puro[9:]}"


def _tel_nove(rng):
    numero = s.fake_phone(rng, "puro")
    return f"+55 ({numero[:2]}) {numero[2]} {numero[3:7]}-{numero[7:]}"


# Formatos de texto variados (rodada 4 da simulação).
CENARIOS += [
    Cenario(
        "Formato: tabela em Markdown",
        "| Nome | CPF | Telefone |\n|---|---|---|\n| <<nome>> | <<cpf>> | <<tel>> |\n| <<nome2>> | <<cpf2>> | <<tel2>> |\n\n"
        "Resuma a tabela.",
        {"nome": ("PESSOA", _nome), "cpf": ("CPF", s.fake_cpf), "tel": ("TELEFONE", s.fake_phone),
         "nome2": ("PESSOA", _nome), "cpf2": ("CPF", s.fake_cpf), "tel2": ("TELEFONE", s.fake_phone)},
        manter=["| Nome | CPF | Telefone |"],
    ),
    Cenario(
        "Formato: HTML de cadastro",
        "<div class=\"cliente\"><p>Nome: <b><<nome>></b></p><p>E-mail: <a href=\"mailto:<<email>>\"><<email>></a></p>"
        "<p>Tel: <<tel>></p></div>\nConverta para Markdown.",
        {"nome": ("PESSOA", _nome), "email": ("EMAIL", s.fake_email), "tel": ("TELEFONE", s.fake_phone)},
        manter=["<div class=\"cliente\">"],
    ),
    Cenario(
        "Formato: XML de nota fiscal",
        "<dest><CPF><<cpf>></CPF><xNome><<nome>></xNome><enderDest><xLgr><<rua>></xLgr><nro>120</nro><CEP><<cep>></CEP>"
        "<fone><<tel>></fone></enderDest><email><<email>></email></dest>\nPor que a SEFAZ rejeita esse XML?",
        {"cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)), "nome": ("PESSOA", _nome),
         "rua": ("ENDERECO", lambda rng: s.fake_address(rng, number=False)),
         "cep": ("CEP", lambda rng: s.fake_cep(rng, False)), "tel": ("TELEFONE", lambda rng: s.fake_phone(rng, "puro")),
         "email": ("EMAIL", s.fake_email)},
        manter=["<nro>120</nro>", "SEFAZ"],
    ),
    Cenario(
        "Formato: declaração em maiúsculas",
        "DECLARAÇÃO DE RESIDÊNCIA\n\nEU, <<nome>>, PORTADOR DO CPF <<cpf>>, DECLARO PARA OS DEVIDOS FINS QUE RESIDO NA "
        "<<endereco>>, CEP <<cep>>.\n\nCorrija a gramática.",
        {"nome": ("PESSOA", _maiusculo), "cpf": ("CPF", s.fake_cpf),
         "endereco": ("ENDERECO", lambda rng: s.fake_address(rng).upper()), "cep": ("CEP", s.fake_cep)},
        manter=["DECLARAÇÃO DE RESIDÊNCIA", "DEVIDOS FINS"],
    ),
    Cenario(
        "Formato: WhatsApp com emojis",
        "Oi!! 😊 sou a <<p1>> 🙋‍♀️ meu cpf ➡️ <<cpf>> e zap 📱 <<tel>> 🙏 preciso remarcar a consulta",
        {"p1": ("PESSOA", _primeiro), "cpf": ("CPF", s.fake_cpf), "tel": ("TELEFONE", s.fake_phone)},
        manter=["remarcar a consulta"],
    ),
    Cenario(
        "Formato: digitação descuidada",
        "cpf:<<cpf>> tel(11)<<tel>> email <<email>> cpf do marido <<cpf2>> fone <<tel2>>",
        {"cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)),
         "tel": ("TELEFONE", lambda rng: f"9{rng.randint(6000, 9999)}-{rng.randint(1000, 9999)}"),
         "email": ("EMAIL", lambda rng: s.fake_email(rng).upper()), "cpf2": ("CPF", _cpf_espacado),
         "tel2": ("TELEFONE", _tel_nove)},
    ),
    Cenario(
        "Formato: JSON escapado em log",
        "2026-11-19T10:15:32Z ERROR {\"msg\":\"falha no cadastro\",\"payload\":\"{\\\"nome\\\":\\\"<<nome>>\\\","
        "\\\"cpf\\\":\\\"<<cpf>>\\\",\\\"email\\\":\\\"<<email>>\\\"}\"}\nO que causou o erro?",
        {"nome": ("PESSOA", _nome), "cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)), "email": ("EMAIL", s.fake_email)},
        manter=["falha no cadastro", "2026-11-19T10:15:32Z"],
    ),
    Cenario(
        "Formato: dados na URL",
        "O checkout quebra nesta URL: https://loja.example/checkout?email=<<email_url>>&cpf=<<cpf>>&nome=<<nome_url>>"
        "&cupom=BLACK10",
        {"email_url": ("EMAIL", lambda rng: s.fake_email(rng).replace("@", "%40")),
         "cpf": ("CPF", lambda rng: s.fake_cpf(rng, False)),
         "nome_url": ("PESSOA", lambda rng: _nome(rng, 2).replace(" ", "+"))},
        manter=["cupom=BLACK10"],
    ),
    Cenario(
        "Formato: autenticação Basic",
        "curl -H \"Authorization: Basic <<basic>>\" https://api.empresa.example/v1/relatorios dá 401.",
        {"basic": ("TOKEN", lambda rng: _b64(rng, 28) + "==")},
        manter=["401"],
    ),
]


@dataclass
class Caso:
    perfil: str
    texto: str
    esperados: list[tuple[str, str]]  # (rótulo, valor)
    manter: list[str]
    fundo: str = ""  # o texto do modelo, sem os dados


def montar(cenario: Cenario, rng: random.Random) -> Caso:
    valores: dict[str, str] = {}
    for campo, (_rotulo, gerar) in cenario.campos.items():
        if campo.startswith("email") and campo not in valores:
            nome = valores.get("nome" + campo.removeprefix("email"))
            valores[campo] = s.fake_email(rng, name=nome) if nome else gerar(rng)
        else:
            valores[campo] = gerar(rng)
    texto = re.sub(r"<<(\w+)>>", lambda m: valores[m.group(1)], cenario.texto)
    esperados = [(cenario.campos[campo][0], valor) for campo, valor in valores.items() if cenario.campos[campo][0]]
    fundo = re.sub(r"<<\w+>>", " ", cenario.texto)
    return Caso(cenario.perfil, texto, esperados, cenario.manter, fundo)


_LIGACOES = {"da", "de", "do", "das", "dos", "e"}


def vazou(rotulo: str, valor: str, saida: str, fundo: str = "") -> bool:
    if rotulo == "CHAVE_PRIVADA":
        return any(linha in saida for linha in valor.splitlines()[1:-1])
    if rotulo == "PESSOA":
        # Um sobrenome que sobra já identifica: confere cada palavra do nome. A palavra que o modelo do texto já
        # tem ("Certidão de nascimento" e a sobrenome Nascimento) só conta se aparecer mais vezes que no modelo.
        def vezes(palavra, texto):
            return len(re.findall(rf"(?<!\w){re.escape(palavra)}(?!\w)", texto, re.IGNORECASE))
        return any(vezes(p, saida) > vezes(p, fundo)
                   for p in valor.split() if p.lower() not in _LIGACOES and len(p) > 2)
    return valor in saida


def rodar_js(textos: list[str]) -> list[str]:
    script = ("import('./js/dist/index.js').then(m => { let d = ''; process.stdin.on('data', c => d += c); "
              "process.stdin.on('end', () => { const t = JSON.parse(d); "
              "console.log(JSON.stringify(t.map(x => new m.Veu().anonymize(x).text))); }); });")
    feito = subprocess.run(["node", "-e", script], input=json.dumps(textos), capture_output=True, text=True,
                           encoding="utf-8", cwd=ROOT, check=True)
    return json.loads(feito.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rodadas", type=int, default=3)
    parser.add_argument("--semente", type=int, default=2026)
    parser.add_argument("--sem-js", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--detalhes", action="store_true", help="mostra o texto protegido de cada caso com problema")
    args = parser.parse_args()

    rng = random.Random(args.semente)
    casos = [montar(c, rng) for _ in range(args.rodadas) for c in CENARIOS]
    veu = Veu()
    saidas_js = [] if args.sem_js else rodar_js([c.texto for c in casos])

    total = {"casos": len(casos), "esperados": 0, "vazamentos": 0, "sugestoes": 0, "exageros": 0, "volta": 0,
             "js_diferente": 0}
    problemas = []
    for i, caso in enumerate(casos):
        resultado = veu.anonymize(caso.texto)
        saida = resultado.text
        achados = []
        for rotulo, valor in caso.esperados:
            if rotulo.endswith("?"):
                if vazou(rotulo, valor, saida, caso.fundo):
                    total["sugestoes"] += 1
                    achados.append(f"sugestão  {rotulo[:-1]}: {valor}")
                continue
            total["esperados"] += 1
            if vazou(rotulo, valor, saida, caso.fundo):
                total["vazamentos"] += 1
                achados.append(f"VAZOU     {rotulo}: {valor}")
        for trecho in caso.manter:
            if trecho in caso.texto and trecho not in saida:
                total["exageros"] += 1
                achados.append(f"EXAGERO   escondeu \"{trecho}\"")
        # A IA responde usando os marcadores; a volta tem que trazer os dados reais.
        marcadores = list(dict.fromkeys(re.findall(r"\[[A-Z_]+_\d+\]", saida)))
        resposta = "Resumo: " + ", ".join(marcadores) + "." if marcadores else "Resumo: nada a esconder."
        reais = {r.replacement: r.entity.text for r in resultado.replacements}
        esperado = "Resumo: " + ", ".join(reais.get(m, m) for m in marcadores) + "." if marcadores else resposta
        # Dentro de links o Véu não devolve dados reais (proteção contra roubo por link); para conferir que os
        # dados estão íntegros, a volta do texto inteiro libera os links.
        resultado.vault.policy = RestorePolicy(links=True)
        if resultado.restore(resposta) != esperado or resultado.restore(saida) != caso.texto:
            total["volta"] += 1
            achados.append("VOLTA     a restauração não devolveu o texto original")
        if saidas_js and saidas_js[i] != saida:
            total["js_diferente"] += 1
            achados.append("JS        a versão JavaScript deu outro resultado")
        if achados:
            problemas.append({"perfil": caso.perfil, "achados": achados, "texto": caso.texto, "saida": saida,
                              "saida_js": saidas_js[i] if saidas_js else None})

    print(f"{total['casos']} casos de {len(CENARIOS)} perfis ({args.rodadas} rodadas, semente {args.semente})")
    vaz = 100 * total["vazamentos"] / max(total["esperados"], 1)
    print(f"vazamentos: {total['vazamentos']} de {total['esperados']} dados ({vaz:.1f}%) | exageros: "
          f"{total['exageros']} | volta com erro: {total['volta']} | JS diferente: {total['js_diferente']} | "
          f"sugestões: {total['sugestoes']}")
    por_perfil: dict[str, list[str]] = {}
    for p in problemas:
        por_perfil.setdefault(p["perfil"], []).extend(p["achados"])
    for perfil, achados in por_perfil.items():
        print(f"\n## {perfil}")
        for achado in dict.fromkeys(achados):
            print(f"  {achado}")
    if args.detalhes:
        for p in problemas:
            print(f"\n--- {p['perfil']}\n{p['saida']}")
            if p["saida_js"] and p["saida_js"] != p["saida"]:
                print(f"--- JS:\n{p['saida_js']}")
    if args.json:
        args.json.write_text(json.dumps({"total": total, "problemas": problemas}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
