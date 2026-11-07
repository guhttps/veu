"""Conjunto de desafio congelado: escrito à mão em 07/11/2026, antes das melhorias de nomes e endereços.

Mede a generalização do Véu em textos que nenhum detector viu enquanto era ajustado. Regras:

- Não ajuste detectores olhando estes casos (como VALIDATION_TEMPLATES no gerador).
- Não edite os casos: um teste confere o sha256 do conjunto. Casos novos vão para um conjunto novo (desafio_v2).
- Todos os valores são fictícios: os documentos têm dígito verificador válido, mas foram gerados ao acaso.

Cada caso lista, em ordem, os trechos que DEVEM ser escondidos. Textos sem trechos medem falsos positivos.
"""

from __future__ import annotations

import hashlib
import json

from veu.bench.generator import Sample

VERSION = "desafio_v1"

CASES: list[tuple[str, list[tuple[str, str]]]] = [
    # Conversas informais (WhatsApp, chat de atendimento)
    ("kkkk a kamilly esqueceu o carregador aqui dnv", [("kamilly", "PESSOA")]),
    ("bom dia! aqui é o enzo gabriel, filho da dona cleide", [("enzo gabriel", "PESSOA"), ("cleide", "PESSOA")]),
    ("manda o pix pro thiaguinho q ele paga o churras", [("thiaguinho", "PESSOA")]),
    ("Oii, sou a Ayla, mãe do Anthony do 3º ano B", [("Ayla", "PESSOA"), ("Anthony", "PESSOA")]),
    ("meu cpf é 967 029 433 93, pode conferir?", [("967 029 433 93", "CPF")]),
    ("me chama no zap 11 9 8123-4567 depois das 18h", [("11 9 8123-4567", "TELEFONE")]),
    ("o email dela é lu.martins.dev@example.com mas ela n responde", [("lu.martins.dev@example.com", "EMAIL")]),
    ("A Heloísa Cristina Braga pediu reembolso e o Davi Lucca vai aprovar.",
     [("Heloísa Cristina Braga", "PESSOA"), ("Davi Lucca", "PESSOA")]),
    # Nomes de outras origens
    ("Reunião com Kenji Watanabe e Priya Raghunathan às 15h.", [("Kenji Watanabe", "PESSOA"),
                                                                ("Priya Raghunathan", "PESSOA")]),
    ("O contrato foi assinado por Mohammed Al-Rashid e Olga Kowalczyk.",
     [("Mohammed Al-Rashid", "PESSOA"), ("Olga Kowalczyk", "PESSOA")]),
    ("Atendente: Jennifer O'Connor. Cliente: Sebastián Ortega Ruiz.",
     [("Jennifer O'Connor", "PESSOA"), ("Sebastián Ortega Ruiz", "PESSOA")]),
    # Documentos em formatos menos comuns
    ("CPF: 184.123.***-**, conforme exibido no portal.", [("184.123.***-**", "CPF")]),
    ("Fornecedor CNPJ 32 197 310 0001 34, nota emitida ontem.", [("32 197 310 0001 34", "CNPJ")]),
    ("PIS/PASEP 762.43701.09-8 do colaborador novo.", [("762.43701.09-8", "PIS")]),
    ("CNH nº 91036959969, categoria AB, validade 2030.", [("91036959969", "CNH")]),
    ("Título eleitoral 0674 9900 0175, zona 0123.", [("0674 9900 0175", "TITULO_ELEITOR")]),
    ("Renavam do veículo: 69744314612.", [("69744314612", "RENAVAM")]),
    ("CPF 25283426912 / CNPJ 45559704000137", [("25283426912", "CPF"), ("45559704000137", "CNPJ")]),
    # Endereços
    ("Entregar na Quadra 204 Sul, Alameda 12, lote 8, Palmas - TO.", [("Quadra 204 Sul, Alameda 12, lote 8", "ENDERECO")]),
    ("Mora no Conjunto Residencial Bela Vista, casa 15, bloco C.",
     [("Conjunto Residencial Bela Vista, casa 15, bloco C", "ENDERECO")]),
    ("Endereço: Estrada do Cafundá, 1200 - Taquara, Rio de Janeiro/RJ, CEP 22725-031",
     [("Estrada do Cafundá, 1200", "ENDERECO"), ("22725-031", "CEP")]),
    ("SQN 308 Bloco F apto 104, Brasília", [("SQN 308 Bloco F apto 104", "ENDERECO")]),
    # Dados estruturados
    ('{"cliente": "Rogério Tavares", "cpf": "018.833.096-89", "fone": "+55 21 99876-5432"}',
     [("Rogério Tavares", "PESSOA"), ("018.833.096-89", "CPF"), ("+55 21 99876-5432", "TELEFONE")]),
    ("nome;cpf;email\nBeatriz Nogueira;80782922872;bia.nogueira@example.org",
     [("Beatriz Nogueira", "PESSOA"), ("80782922872", "CPF"), ("bia.nogueira@example.org", "EMAIL")]),
    ("2026-11-03T10:22:01Z INFO login ok user=valeria.prates@example.com ip=187.45.20.113",
     [("valeria.prates@example.com", "EMAIL"), ("187.45.20.113", "IP")]),
    # Saúde, jurídico e financeiro
    ("Paciente Benedita Aparecida dos Santos, 67 anos, deu entrada às 3h.",
     [("Benedita Aparecida dos Santos", "PESSOA")]),
    ("Autor: Edvaldo Pereira Lins, representado pela defensoria.",
     [("Edvaldo Pereira Lins", "PESSOA")]),
    ("Cartão final 4242, número completo 5555 5555 5555 4444, titular Marcos V. Teles.",
     [("5555 5555 5555 4444", "CARTAO_CREDITO"), ("Marcos V. Teles", "PESSOA")]),
    ("Ag. 3456-7 C/C 12345-6, favorecida Joana Prado.", [("3456-7", "CONTA_BANCARIA"),
                                                         ("12345-6", "CONTA_BANCARIA"), ("Joana Prado", "PESSOA")]),
    ("Nasci em 14/02/1990 e meu RG é 34.567.890-1.", [("14/02/1990", "DATA_NASCIMENTO"), ("34.567.890-1", "RG")]),
    # Segredos
    ("a senha do wifi do escritório é Pato#Azul77, não espalha", [("Pato#Azul77", "SENHA")]),
    ("export DATABASE_URL=postgres://app:S3gr3d0!@db.interno:5432/prod",
     [("postgres://app:S3gr3d0!@db.interno:5432/prod", "URL_CONEXAO")]),
    ("client_secret: 8f3c2b9e-7a41-4d6f-b2e8-91c0d5a7f3e2", [("8f3c2b9e-7a41-4d6f-b2e8-91c0d5a7f3e2", "SEGREDO")]),
    # Sem dados pessoais (falsos positivos)
    ("A Rosa dos Ventos aponta para o norte magnético.", []),
    ("O Grêmio venceu o Inter por 2 a 1 no Beira-Rio.", []),
    ("Agência de turismo em Natal oferece passeio às dunas de Genipabu.", []),
    ("O pedido 4815162342 foi enviado pelos Correios.", []),
    ("Leia o capítulo 3 de Dom Casmurro até sexta.", []),
    ("A temperatura máxima prevista para amanhã é de 31 graus em Cuiabá.", []),
    ("Versão 2.14.0 lançada com correções no módulo de pagamentos.", []),
    ("Reunião de alinhamento às 9h na sala Ipê Amarelo.", []),
]


def challenge_samples() -> list[Sample]:
    samples = []
    for text, expected in CASES:
        entities = []
        cursor = 0
        for snippet, label in expected:
            start = text.index(snippet, cursor)
            entities.append((start, start + len(snippet), label))
            cursor = start + len(snippet)
        samples.append(Sample(text, entities, VERSION))
    return samples


def fingerprint() -> str:
    """sha256 dos casos: muda se alguém editar o conjunto congelado."""
    return hashlib.sha256(json.dumps(CASES, ensure_ascii=False).encode()).hexdigest()
