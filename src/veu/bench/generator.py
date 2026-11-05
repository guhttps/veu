"""Gerador do conjunto de avaliação: textos realistas com dados pessoais falsos e anotados."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from veu import surrogates as fake
from veu._text import fold
from veu.recognizers.base import folded_set

# Nomes que NÃO estão nas listas do detector: medem a detecção por contexto, não só por lista.
HELD_OUT_FIRST_NAMES = (
    "Kauê", "Thayná", "Ludmila", "Wendel", "Railson", "Jhonatan", "Kethelyn", "Dandara", "Iasmin", "Maiara",
    "Taynara", "Elisvaldo", "Josivaldo", "Crislaine", "Gleice", "Jucilene", "Edivaldo", "Rosivaldo", "Ozéias",
    "Gerusa", "Lucinéia", "Valdenice", "Ivaneide", "Josenildo", "Kleber", "Anelise", "Gislene", "Joelma",
    "Luzinete", "Edjane",
)

TEMPLATES: list[tuple[str, str]] = [
    ("atendimento", "Olá, meu nome é {PESSOA} e meu CPF é {CPF}. Fiz o pedido {pedido} no valor de {valor} e até agora não chegou."),
    ("atendimento", "Cliente {PESSOA} ligou do número {TELEFONE} reclamando da cobrança de {valor}. Protocolo {protocolo}."),
    ("atendimento", "Bom dia! Aqui é a {PESSOA_NOME}, quero trocar o e-mail da minha conta para {EMAIL}."),
    ("atendimento", "Pode enviar o boleto para {EMAIL}? Meu CPF é {CPF_SEM} e o telefone {TELEFONE_INTL}."),
    ("atendimento", "Prezado(a) {PESSOA}, seu pedido {pedido} com {produto} foi enviado para {ENDERECO}, CEP {CEP}."),
    ("atendimento", "Atendimento {protocolo}: a cliente informou que mora na {ENDERECO} e prefere contato pelo WhatsApp {TELEFONE}."),
    ("atendimento", "Solicito o cancelamento do cartão {CARTAO}. Titular: {PESSOA}."),
    ("conversa", "oi {PESSOA_MIN_NOME} tudo bem? me passa sua chave pix: {CHAVE_PIX}"),
    ("conversa", "falei com {PESSOA_MIN} ontem, ela pediu pra ligar no {TELEFONE}"),
    ("conversa", "bom dia {PESSOA_MIN_NOME}! o cpf dela é {CPF_SEM}, confere?"),
    ("saude", "Paciente {PESSOA}, nascido em {NASCIMENTO}, cartão SUS {CNS}, deu entrada no {empresa} às {hora}."),
    ("saude", "Prontuário: {PESSOA}, data de nascimento: {NASCIMENTO}. Responsável: {PESSOA}, telefone {TELEFONE}."),
    ("saude", "Dra. {PESSOA_RARA} solicitou exames para o paciente {PESSOA} (CNS {CNS})."),
    ("juridico", "Processo nº {PROCESSO}. Autor: {PESSOA}, CPF {CPF}, residente na {ENDERECO}. Réu: {empresa}, CNPJ {CNPJ}."),
    ("juridico", "{PESSOA}, portador do RG {RG} e inscrito no CPF sob o nº {CPF}, vem respeitosamente requerer a revisão."),
    ("juridico", "Nos autos do processo {PROCESSO}, a testemunha {PESSOA_RARA} declarou ter visto o veículo de placa {PLACA}."),
    ("rh", "Admissão: {PESSOA}, CPF {CPF}, PIS {PIS}, título de eleitor {TITULO}. Salário de {valor}."),
    ("rh", "Dados bancários do colaborador {PESSOA}: agência {AGENCIA}, conta {CONTA}. Data de nascimento: {NASCIMENTO}."),
    ("veiculos", "Veículo placa {PLACA}, RENAVAM {RENAVAM}, proprietário {PESSOA}, CNH {CNH}."),
    ("financeiro", "Pagamento via Pix para a chave {CHAVE_PIX} confirmado em {data}. Valor: {valor}."),
    ("financeiro", "Transferência de {valor} para {PESSOA}, CPF {CPF}, conta {CONTA}."),
    ("ti", "Login suspeito do usuário {EMAIL} a partir do IP {IP} às {hora} do dia {data}."),
    ("ti", "Erro ao processar o pedido {pedido}: cliente {PESSOA} (CPF {CPF_SEM}), versão {versao}."),
    ("empresas", "Nota fiscal emitida para {empresa}, CNPJ {CNPJ_ALFA}, com sede na {ENDERECO}."),
    ("contratos", "Locador: {PESSOA}, CPF {CPF}. Locatário: {PESSOA}, RG {RG}. Imóvel na {ENDERECO}, CEP {CEP}."),
    ("viagem", "Reserva confirmada para {PESSOA}, passaporte {PASSAPORTE}, voo para {cidade} em {data}."),
    ("email", "De: {PESSOA} <{EMAIL}>\nAssunto: Pedido {pedido}\n\nOlá, segue meu endereço novo: {ENDERECO}, {cidade}.\nAtt, {PESSOA_NOME}"),
    ("email", "Oi pessoal, o {PESSOA_NOME} vai substituir a {PESSOA_NOME} na reunião de {data}. Qualquer coisa, liguem no {TELEFONE}."),
    ("formulario", "CPF: {CPF}; CNPJ: {CNPJ}; Tel.: {TELEFONE}; E-mail: {EMAIL}; CEP: {CEP}"),
    ("formulario", "NOME: {PESSOA_MAIUSCULO}\nCPF: {CPF}\nENDEREÇO: {ENDERECO}"),
    ("atendimento", "Sra. {PESSOA_RARA}, sua consulta foi remarcada para {data} às {hora}."),
    ("rh", "A colaboradora {PESSOA_RARA} {SOBRENOME} pediu férias a partir de {data}."),
    # Textos sem dados pessoais: medem os falsos positivos.
    ("sem_dados", "O pedido {pedido} de {produto} foi entregue em {cidade} no dia {data}, às {hora}. Valor total: {valor}."),
    ("sem_dados", "A {empresa} anunciou resultados do trimestre: receita de {valor} e crescimento em {cidade}."),
    ("sem_dados", "Atualize para a versão {versao}. O protocolo de atendimento é {protocolo}."),
    ("sem_dados", "Reunião marcada para {data} às {hora} na sede da {empresa} em {cidade}."),
    ("sem_dados", "O produto {codigo} está em promoção por {valor} até {data}."),
    ("sem_dados", "Rosa é a cor do ano, segundo a {empresa}. Vitória do time em {cidade}!"),
    ("sem_dados", "Fizemos o deploy em 3 regiões e o tempo de resposta caiu 40%. Ticket {pedido}."),
    ("sem_dados", "Avenida Paulista, Rua Augusta e Praça da Sé são pontos turísticos de São Paulo."),
]

# Conjunto de validação: modelos escritos depois do ajuste do detector e nunca usados para ajustá-lo.
# Mede a generalização para textos novos (o conjunto de desenvolvimento acima tende a ficar perto de 100%).
VALIDATION_TEMPLATES: list[tuple[str, str]] = [
    ("financeiro", "Segue o comprovante. Favorecido: {PESSOA}, chave Pix {EMAIL}."),
    ("rh", "Informo que {PESSOA_RARA} não compareceu ao plantão de {data}."),
    ("rh", "Encaminho o currículo de {PESSOA}: tel {TELEFONE}, nasc. {NASCIMENTO}, residente à {ENDERECO}."),
    ("saude", "Boa tarde, gostaria de agendar uma consulta para minha filha {PESSOA_NOME}. Meu número é {TELEFONE}."),
    ("logistica", "Ref.: NF {pedido}. Destinatário {PESSOA}, {ENDERECO}, {cidade}/SP, CEP {CEP}."),
    ("conversa", "kkkk o {PESSOA_MIN_NOME} esqueceu a senha de novo, manda no {EMAIL}"),
    ("financeiro", "Consta débito no CPF {CPF} em nome de {PESSOA_MAIUSCULO}."),
    ("atendimento", "Autorizo {PESSOA} (RG {RG}) a retirar minha encomenda."),
    ("veiculos", "Motorista {PESSOA_RARA}, CNH {CNH}, veículo {PLACA}."),
    ("formulario", "Ficha: {PESSOA} | {CPF_SEM} | {TELEFONE} | {EMAIL}"),
    ("financeiro", "Dados para reembolso: banco 341, agência {AGENCIA}, conta {CONTA}, titular {PESSOA}."),
    ("ti", "O servidor {IP} recebeu 3 tentativas de login de {EMAIL}."),
    ("empresas", "Prezados, a empresa {empresa} (CNPJ {CNPJ}) solicitou orçamento de {produto}."),
    ("contratos", "Contrato nº {pedido}: as partes {PESSOA} e {PESSOA} acordam o seguinte."),
    ("saude", "Encaminho a paciente {PESSOA}, CNS {CNS}, para avaliação cardiológica."),
    ("juridico", "Intime-se {PESSOA}, CPF {CPF}, no endereço {ENDERECO}, nos autos {PROCESSO}."),
    ("sem_dados", "O frete para {cidade} custa {valor} e chega em 5 dias úteis."),
    ("sem_dados", "Lembrete: a manutenção do sistema ocorre em {data} das {hora} às 23h59."),
    ("sem_dados", "O Flamengo venceu o Palmeiras por 2 a 1 no Maracanã."),
    ("sem_dados", "A Petrobras e a Vale lideraram as altas da bolsa nesta segunda-feira."),
]

SLOT_LABELS = {
    "PESSOA": "PESSOA", "PESSOA_NOME": "PESSOA", "PESSOA_MIN": "PESSOA", "PESSOA_MIN_NOME": "PESSOA",
    "PESSOA_RARA": "PESSOA", "PESSOA_MAIUSCULO": "PESSOA", "SOBRENOME": "PESSOA",
    "CPF": "CPF", "CPF_SEM": "CPF", "CNPJ": "CNPJ", "CNPJ_ALFA": "CNPJ", "TELEFONE": "TELEFONE",
    "TELEFONE_INTL": "TELEFONE", "EMAIL": "EMAIL", "ENDERECO": "ENDERECO", "CEP": "CEP", "PLACA": "PLACA",
    "CARTAO": "CARTAO_CREDITO", "RG": "RG", "CNH": "CNH", "PIS": "PIS", "CNS": "CNS", "TITULO": "TITULO_ELEITOR",
    "RENAVAM": "RENAVAM", "NASCIMENTO": "DATA_NASCIMENTO", "CHAVE_PIX": "CHAVE_PIX", "IP": "IP",
    "CONTA": "CONTA_BANCARIA", "AGENCIA": "CONTA_BANCARIA", "PROCESSO": "PROCESSO", "PASSAPORTE": "PASSAPORTE",
}
COMPANIES = ("Hospital Santa Luzia", "Mercado Bom Preço", "Tech Soluções Ltda", "Construtora Horizonte",
             "Farmácia Popular do Centro", "Clínica Vida Plena", "Padaria Pão Dourado", "Escola Nova Era")
PRODUCTS = ("notebook", "fone de ouvido", "cafeteira", "geladeira", "kit de ferramentas", "tênis de corrida",
            "smartphone", "cadeira gamer")
CITIES = ("São Paulo", "Recife", "Curitiba", "Belo Horizonte", "Porto Alegre", "Salvador", "Manaus", "Goiânia",
          "Florianópolis", "Fortaleza")


@dataclass
class Sample:
    text: str
    entities: list[tuple[int, int, str]] = field(default_factory=list)
    category: str = ""

    def to_dict(self) -> dict:
        return {
            "texto": self.text,
            "categoria": self.category,
            "entidades": [{"inicio": s, "fim": e, "entidade": label} for s, e, label in self.entities],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Sample:
        entities = [(item["inicio"], item["fim"], item["entidade"]) for item in data.get("entidades", [])]
        return cls(data["texto"], entities, data.get("categoria", ""))


def _held_out_names() -> list[str]:
    known = folded_set("first_names.txt")
    return [name for name in HELD_OUT_FIRST_NAMES if fold(name) not in known]


def _slot(slot: str, rng: random.Random) -> str:
    if slot == "PESSOA":
        return fake.fake_name(rng, words=rng.choice((2, 2, 3)))
    if slot == "PESSOA_NOME":
        return rng.choice(fake.first_names())
    if slot == "PESSOA_MIN":
        return fake.fake_name(rng, words=2).lower()
    if slot == "PESSOA_MIN_NOME":
        return rng.choice(fake.first_names()).lower()
    if slot == "PESSOA_RARA":
        return f"{rng.choice(_held_out_names())} {rng.choice(fake.surnames())}"
    if slot == "PESSOA_MAIUSCULO":
        return fake.fake_name(rng, words=3).upper()
    if slot == "SOBRENOME":
        return rng.choice(fake.surnames())
    generators = {
        "CPF": lambda: fake.fake_cpf(rng),
        "CPF_SEM": lambda: fake.fake_cpf(rng, formatted=False),
        "CNPJ": lambda: fake.fake_cnpj(rng),
        "CNPJ_ALFA": lambda: fake.fake_cnpj(rng, alphanumeric=True),
        "TELEFONE": lambda: fake.fake_phone(rng, rng.choice(("formatado", "formatado", "espacos")), rng.random() < 0.8),
        "TELEFONE_INTL": lambda: fake.fake_phone(rng, "internacional"),
        "EMAIL": lambda: fake.fake_email(rng),
        "ENDERECO": lambda: _address(rng),
        "CEP": lambda: fake.fake_cep(rng),
        "PLACA": lambda: fake.fake_plate(rng, mercosul=rng.random() < 0.6),
        "CARTAO": lambda: fake.fake_card(rng),
        "RG": lambda: fake.fake_rg(rng, formatted=rng.random() < 0.7),
        "CNH": lambda: fake.fake_cnh(rng),
        "PIS": lambda: fake.fake_pis(rng, formatted=rng.random() < 0.5),
        "CNS": lambda: fake.fake_cns(rng, formatted=rng.random() < 0.5),
        "TITULO": lambda: fake.fake_titulo(rng, formatted=rng.random() < 0.5),
        "RENAVAM": lambda: fake.fake_renavam(rng),
        "NASCIMENTO": lambda: fake.fake_birthdate(rng, rng.choice(("barras", "barras", "extenso"))),
        "CHAVE_PIX": lambda: fake.fake_pix_key(rng),
        "IP": lambda: fake.fake_ipv4(rng) if rng.random() < 0.8 else fake.fake_ipv6(rng),
        "CONTA": lambda: fake.fake_account(rng),
        "AGENCIA": lambda: str(rng.randint(1000, 9999)),
        "PROCESSO": lambda: fake.fake_processo(rng),
        "PASSAPORTE": lambda: fake.fake_passport(rng),
        "pedido": lambda: str(rng.randint(10_000, 9_999_999)),
        "protocolo": lambda: f"{rng.randint(2024, 2026)}{rng.randint(10_000_000, 99_999_999)}",
        "valor": lambda: f"R$ {rng.randint(10, 9_999)},{rng.randint(0, 99):02d}",
        "data": lambda: f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(2024, 2027)}",
        "hora": lambda: f"{rng.randint(7, 22)}h{rng.choice(('00', '15', '30', '45'))}",
        "cidade": lambda: rng.choice(CITIES),
        "empresa": lambda: rng.choice(COMPANIES),
        "produto": lambda: rng.choice(PRODUCTS),
        "codigo": lambda: f"SKU-{rng.randint(10_000, 99_999)}",
        "versao": lambda: f"{rng.randint(1, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}",
    }
    return generators[slot]()


def _address(rng: random.Random) -> str:
    style = rng.random()
    if style < 0.15:
        street = f"Rua {rng.randint(1, 31)} de {rng.choice(('Março', 'Maio', 'Setembro', 'Novembro'))}"
        address = f"{street}, {rng.randint(1, 2000)}"
    else:
        address = fake.fake_address(rng)
    if rng.random() < 0.35:
        address += rng.choice((f", apto {rng.randint(11, 304)}", f", casa {rng.randint(1, 9)}",
                               f", bloco {rng.choice('ABCD')}"))
    return address


_SLOT = re.compile(r"\{([A-Za-z_]+)\}")


def render(template: str, rng: random.Random) -> tuple[str, list[tuple[int, int, str]]]:
    output, entities, position = [], [], 0
    length = 0
    for match in _SLOT.finditer(template):
        literal = template[position:match.start()]
        output.append(literal)
        length += len(literal)
        value = _slot(match.group(1), rng)
        label = SLOT_LABELS.get(match.group(1))
        if label:
            entities.append((length, length + len(value), label))
        output.append(value)
        length += len(value)
        position = match.end()
    output.append(template[position:])
    return "".join(output), entities


def generate(count: int = 500, seed: int = 42, validation: bool = False) -> list[Sample]:
    """Gera amostras anotadas. validation=True usa o conjunto de validação (modelos não usados no ajuste)."""
    rng = random.Random(seed)
    templates = VALIDATION_TEMPLATES if validation else TEMPLATES
    samples = []
    for index in range(count):
        category, template = templates[index % len(templates)] if index < len(templates) else rng.choice(templates)
        text, entities = render(template, rng)
        samples.append(Sample(text, entities, category))
    return samples


def save(samples: list[Sample], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n")


def load(path: str | Path) -> list[Sample]:
    with Path(path).open(encoding="utf-8") as handle:
        return [Sample.from_dict(json.loads(line)) for line in handle if line.strip()]
