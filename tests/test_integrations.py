import asyncio
import json
import logging

import httpx
import pytest

PII = [{"role": "user", "content": "Sou a Maria Souza, CPF 529.982.247-25."}]


def openai_upstream(module, seen):
    def handler(request):
        if not request.content:
            return module.Response(200, json={"data": []})
        seen.append(json.loads(request.content))
        if json.loads(request.content).get("stream"):
            chunks = ["Olá [PES", "SOA_1], seu CPF [CPF_", "1] está ok."]
            sse = "".join(
                "data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "m",
                                       "choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]}) + "\n\n"
                for c in chunks
            ) + "data: [DONE]\n\n"
            return module.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
        return module.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Olá [PESSOA_1], CPF [CPF_1]."}}],
        })

    return handler


def anthropic_upstream(module, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "m", "type": "message", "role": "assistant", "model": "c", "content": [], "stop_reason": None,
                "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": "Prezada [PESS"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": "OA_1], CPF [CPF_1]"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": {"output_tokens": 5}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        sse = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return module.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())

    return handler


def test_openai_sdk_with_httpx2_transport():
    openai = pytest.importorskip("openai")
    httpx2 = pytest.importorskip("httpx2")
    from veu.integrations.httpx2 import VeuTransport

    seen = []
    transport = VeuTransport(transport=httpx2.MockTransport(openai_upstream(httpx2, seen)))
    client = openai.OpenAI(api_key="teste", http_client=httpx2.Client(transport=transport))
    reply = client.chat.completions.create(model="m", messages=PII)
    assert reply.choices[0].message.content == "Olá Maria Souza, CPF 529.982.247-25."
    assert seen[-1]["messages"][-1]["content"] == "Sou a [PESSOA_1], CPF [CPF_1]."
    stream = client.chat.completions.create(model="m", messages=PII, stream=True)
    assert "".join(c.choices[0].delta.content or "" for c in stream if c.choices) == (
        "Olá Maria Souza, seu CPF 529.982.247-25 está ok."
    )


def test_async_openai_sdk():
    openai = pytest.importorskip("openai")
    httpx2 = pytest.importorskip("httpx2")
    from veu.integrations.httpx2 import AsyncVeuTransport

    seen = []
    transport = AsyncVeuTransport(transport=httpx2.MockTransport(openai_upstream(httpx2, seen)))
    client = openai.AsyncOpenAI(api_key="teste", http_client=httpx2.AsyncClient(transport=transport))

    async def run():
        stream = await client.chat.completions.create(model="m", messages=PII, stream=True)
        return "".join([chunk.choices[0].delta.content or "" async for chunk in stream if chunk.choices])

    assert asyncio.run(run()) == "Olá Maria Souza, seu CPF 529.982.247-25 está ok."


def test_anthropic_sdk_stream():
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    from veu.integrations.httpx2 import VeuTransport

    seen = []
    transport = VeuTransport(transport=httpx2.MockTransport(anthropic_upstream(httpx2, seen)))
    client = anthropic.Anthropic(api_key="teste", http_client=httpx2.Client(transport=transport))
    with client.messages.stream(model="c", max_tokens=50, messages=PII) as stream:
        text = "".join(stream.text_stream)
    assert text == "Prezada Maria Souza, CPF 529.982.247-25"
    assert seen[-1]["messages"][0]["content"] == "Sou a [PESSOA_1], CPF [CPF_1]."


def test_plain_httpx_transport():
    from veu.integrations.httpx import VeuTransport

    seen = []
    client = httpx.Client(transport=VeuTransport(transport=httpx.MockTransport(openai_upstream(httpx, seen))))
    response = client.post("https://api.groq.com/openai/v1/chat/completions", json={"model": "m", "messages": PII})
    assert response.json()["choices"][0]["message"]["content"] == "Olá Maria Souza, CPF 529.982.247-25."
    assert response.headers["x-veu-entidades"] == "CPF=1, PESSOA=1"
    other = client.get("https://api.groq.com/openai/v1/models")
    assert other.status_code == 200


def test_sdk_helpers_pick_the_right_http_library():
    pytest.importorskip("openai")
    pytest.importorskip("anthropic")
    from veu.integrations.sdk import anthropic_client, openai_client

    assert openai_client(api_key="teste").base_url.host == "api.openai.com"
    assert anthropic_client(api_key="teste").base_url.host == "api.anthropic.com"


def test_logging_filter_hides_personal_data(caplog):
    from veu.integrations.logging import PIIFilter

    logger = logging.getLogger("veu.teste")
    logger.addFilter(PIIFilter())
    with caplog.at_level(logging.INFO, logger="veu.teste"):
        logger.info("Cliente %s com CPF %s entrou", "Maria Souza", "529.982.247-25")
        try:
            raise ValueError("CPF inválido: 529.982.247-25")
        except ValueError:
            logger.exception("falhou")
    assert "Cliente [PESSOA] com CPF [CPF] entrou" in caplog.text
    assert "529.982.247-25" not in caplog.text
