"""veu demonstrar: mostra, sem chave de API, o que chega ao provedor com e sem o Véu.

Sobe um provedor falso na memória, manda a mesma requisição direto e pelo proxy do Véu e confere, valor por valor,
o que o provedor recebeu. Os valores são inventados (CPF válido, mas gerado; chave no formato, mas falsa).
"""

from __future__ import annotations

import asyncio
import json

PLANTED = [
    ("Nome", "Marina Albuquerque", "texto da mensagem"),
    ("CPF", "529.982.247-25", "texto da mensagem"),
    ("Telefone", "(11) 98765-4321", "texto da mensagem"),
    ("E-mail", "marina.albuquerque@example.com", "argumentos de ferramenta"),
    ("Cartão", "4111 1111 1111 1111", "argumentos de ferramenta"),
    ("Chave de API", "sk-" + "proj-" + "Zx9" * 14, "resultado de ferramenta"),
    ("Senha", "Tr0ca@2026!", "resultado de ferramenta"),
]


def _request() -> dict:
    by_place: dict[str, list[str]] = {}
    for _, value, place in PLANTED:
        by_place.setdefault(place, []).append(value)
    return {
        "model": "modelo-falso",
        "messages": [
            {"role": "user", "content": "Resuma o atendimento: " + ", ".join(by_place["texto da mensagem"])},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "buscar_cliente",
                "arguments": json.dumps({"email": by_place["argumentos de ferramenta"][0],
                                         "cartao": by_place["argumentos de ferramenta"][1]}),
            }}]},
            {"role": "tool", "tool_call_id": "c1",
             "content": "OPENAI_API_KEY={} DB_PASSWORD={}".format(*by_place["resultado de ferramenta"])},
        ],
    }


def run() -> int:
    try:
        import httpx

        from veu.config import Config
        from veu.server import create_app
    except ImportError:
        print('A demonstração usa o servidor: pip install "veu[servidor]"')
        return 2

    received: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        received.append(request.content.decode())
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}]})

    async def send() -> None:
        body = _request()
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as direct:
            await direct.post("https://api.openai.com/v1/chat/completions", json=body)
        app = create_app(Config(audit_log=None), upstream_transport=httpx.MockTransport(provider))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as veu:
            await veu.post("/v1/chat/completions", json=body)

    asyncio.run(send())
    direct, protected = received
    width = max(len(name) for name, _, _ in PLANTED)
    print("O que o provedor de IA recebeu, com valores inventados:\n")
    print(f"  {'dado':<{width}}  {'onde':<26} {'direto':<9} pelo Véu")
    leaks = 0
    for name, value, place in PLANTED:
        raw = json.dumps(value)[1:-1]
        in_direct = value in direct or raw in direct
        in_protected = value in protected or raw in protected
        leaks += in_protected
        print(f"  {name:<{width}}  {place:<26} {'VAZOU' if in_direct else 'protegido':<9} "
              f"{'VAZOU' if in_protected else 'protegido'}")
    print()
    if leaks:
        print(f"{leaks} valor(es) passaram pelo Véu.")
        return 1
    print("Pelo Véu, nenhum dos valores chegou ao provedor: ele recebeu só marcadores como [CPF_1].")
    print("A resposta volta com os dados reais para quem chamou. Experimente: veu servir")
    return 0
