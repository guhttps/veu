"""@protect: protege qualquer função que chama um modelo de IA, com qualquer biblioteca.

    pip install veu requests
    python examples/decorador.py          # usa um "modelo" de mentira para mostrar o fluxo
"""

from veu import protect


@protect
def responder(pergunta: str) -> str:
    # Aqui entraria a chamada real (requests, SDK, modelo local...). O texto já chega anonimizado.
    print("o modelo recebeu:", pergunta)
    return "Olá [PESSOA_1], confirmamos o CPF [CPF_1]."


@protect
def responder_em_partes(pergunta: str):
    # Funções geradoras (streaming) também funcionam.
    yield from ["Olá [PES", "SOA_1], tudo ", "certo!"]


print("você recebe:", responder("Sou a Maria Souza, CPF 529.982.247-25"))
print("em partes:", "".join(responder_em_partes("Sou a Maria Souza")))
