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
         "carteira": ("CONVENIO?", lambda rng: "".join(rng.choice("0123456789") for _ in range(17)))},
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


@dataclass
class Caso:
    perfil: str
    texto: str
    esperados: list[tuple[str, str]]  # (rótulo, valor)
    manter: list[str]


def montar(cenario: Cenario, rng: random.Random) -> Caso:
    valores: dict[str, str] = {}
    for campo, (_rotulo, gerar) in cenario.campos.items():
        if campo.startswith("email") and campo not in valores:
            nome = valores.get("nome" + campo.removeprefix("email"))
            valores[campo] = s.fake_email(rng, name=nome) if nome else gerar(rng)
        else:
            valores[campo] = gerar(rng)
    texto = re.sub(r"<<(\w+)>>", lambda m: valores[m.group(1)], cenario.texto)
    esperados = [(cenario.campos[campo][0] or "", valor) for campo, valor in valores.items()]
    return Caso(cenario.perfil, texto, esperados, cenario.manter)


_LIGACOES = {"da", "de", "do", "das", "dos", "e"}


def vazou(rotulo: str, valor: str, saida: str) -> bool:
    if rotulo == "PESSOA":
        # Um sobrenome que sobra já identifica: confere cada palavra do nome.
        return any(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", saida, re.IGNORECASE)
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
                if vazou(rotulo, valor, saida):
                    total["sugestoes"] += 1
                    achados.append(f"sugestão  {rotulo[:-1]}: {valor}")
                continue
            total["esperados"] += 1
            if vazou(rotulo, valor, saida):
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
