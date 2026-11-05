"""Casos difíceis escritos à mão (não gerados por modelo de texto), para complementar o benchmark sintético.

Cada caso lista os trechos que DEVEM ser escondidos. Textos sem trechos testam falsos positivos.
"""

from __future__ import annotations

from veu.bench.generator import Sample

CASES: list[tuple[str, list[tuple[str, str]]]] = [
    ("vc viu a msg da bia? ela disse q o cpf é 52998224725", [("52998224725", "CPF")]),
    ("me liga 11 98765 4321 ou 11987654321", [("11 98765 4321", "TELEFONE"), ("11987654321", "TELEFONE")]),
    ("Meu nome é Kawanny Rodrigues e moro em Natal.", [("Kawanny Rodrigues", "PESSOA")]),
    ("A paciente Graça Maria de Jesus teve alta.", [("Graça Maria de Jesus", "PESSOA")]),
    ("Rosa Pereira ligou pedindo a segunda via.", [("Rosa Pereira", "PESSOA")]),
    ("JOSÉ CARLOS DA SILVA SANTOS\nCPF 529.982.247-25", [("JOSÉ CARLOS DA SILVA SANTOS", "PESSOA"),
                                                         ("529.982.247-25", "CPF")]),
    ("Enviar para Av. Brasil, 1500, sala 3 - Centro.", [("Av. Brasil, 1500, sala 3", "ENDERECO")]),
    ("O CNPJ novo da filial é 12.ABC.345/01DE-35.", [("12.ABC.345/01DE-35", "CNPJ")]),
    ("CPF 123.456.789-10 (digitei errado?)", [("123.456.789-10", "CPF")]),
    ("Placa do carro: BRA2E19. Renavam 00639884962.", [("BRA2E19", "PLACA"), ("00639884962", "RENAVAM")]),
    ("Fala, joão! Tudo certo pra amanhã?", [("joão", "PESSOA")]),
    ("Quem atendeu foi o Dr. Wanderley Fagundes.", [("Wanderley Fagundes", "PESSOA")]),
    ("Pix: maria.lima@example.com", [("maria.lima@example.com", "EMAIL")]),
    ("Conta 12345-6, agência 0001, Banco do Brasil.", [("12345-6", "CONTA_BANCARIA"), ("0001", "CONTA_BANCARIA")]),
    ("Data de nascimento: 7 de setembro de 1985.", [("7 de setembro de 1985", "DATA_NASCIMENTO")]),
    ("Acesso de 2804:14c:5b:a0::1 bloqueado.", [("2804:14c:5b:a0::1", "IP")]),
    ("A reunião com a diretoria será em São José dos Campos.", []),
    ("O Banco do Brasil e o Magazine Luiza anunciaram parceria.", []),
    ("O voo LA3456 sai às 14h30 do portão 12.", []),
    ("A nota fiscal 000123456 tem valor de R$ 1.234,56.", []),
    ("Segue o código de rastreio: NB123456789BR.", []),
    ("Ontem choveu em Vitória e a Vila Velha ficou alagada.", []),
    ("O índice subiu 12,5% em 2025 e deve cair em 2026.", []),
    ("Assistimos ao jogo do Santos contra o Grêmio.", []),
    ("A versão 10.0.19045.3803 do Windows foi lançada.", []),
]


def hard_samples() -> list[Sample]:
    samples = []
    for text, expected in CASES:
        entities = []
        cursor = 0
        for snippet, label in expected:
            start = text.index(snippet, cursor)
            entities.append((start, start + len(snippet), label))
            cursor = start + len(snippet)
        samples.append(Sample(text, entities, "dificil"))
    return samples
