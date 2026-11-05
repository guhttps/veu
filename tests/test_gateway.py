import json
import random

import pytest

from veu import Veu
from veu.gateway import BlockedError, Gateway, detect_adapter
from veu.gateway.sse import encode_event

PII = "Sou a Maria Souza, CPF 529.982.247-25, telefone (11) 91234-5678."


def prepare(path, payload, **options):
    gateway = Gateway(Veu(**options))
    adapter = detect_adapter("POST", path)
    prepared = gateway.prepare(adapter, json.dumps(payload).encode(), path=path)
    return gateway, prepared, json.loads(prepared.body)


def run_stream(gateway, prepared, events, seed=0):
    """Envia os eventos SSE em pedaços de bytes aleatórios e devolve os eventos restaurados."""
    raw = "".join(encode_event(name, data) for name, data in events).encode()
    transformer = gateway.stream(prepared)
    rng = random.Random(seed)
    output, position = b"", 0
    while position < len(raw):
        size = rng.randint(1, 9)
        output += transformer.feed(raw[position:position + size])
        position += size
    output += transformer.close()
    parsed = []
    for block in output.decode().split("\n\n"):
        if not block.strip():
            continue
        name = None
        data = []
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        text = "\n".join(data)
        parsed.append((name, text if text == "[DONE]" else json.loads(text)))
    return parsed


def test_routing_by_path():
    assert detect_adapter("POST", "/v1/chat/completions").name == "openai-chat"
    assert detect_adapter("POST", "/api/chat/completions").name == "openai-chat"
    assert detect_adapter("POST", "/v1/completions").name == "openai-completions"
    assert detect_adapter("POST", "/v1/responses").name == "openai-responses"
    assert detect_adapter("POST", "/v1/embeddings").name == "openai-embeddings"
    assert detect_adapter("POST", "/v1/messages").name == "anthropic-messages"
    assert detect_adapter("POST", "/v1beta/models/gemini-2.5-flash:generateContent").name == "gemini"
    assert detect_adapter("GET", "/v1/models") is None
    assert detect_adapter("POST", "/v1/audio/transcriptions") is None


def test_openai_chat_masks_all_text_fields_and_adds_instruction():
    payload = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "Você é um atendente."},
            {"role": "user", "content": [{"type": "text", "text": PII}, {"type": "image_url", "image_url": {"url": "x"}}]},
            {"role": "assistant", "tool_calls": [{"id": "1", "type": "function",
                                                  "function": {"name": "buscar", "arguments": '{"cpf": "529.982.247-25"}'}}]},
            {"role": "tool", "tool_call_id": "1", "content": "Cliente Maria Souza encontrada."},
        ],
    }
    _, prepared, sent = prepare("/v1/chat/completions", payload)
    body = json.dumps(sent, ensure_ascii=False)
    assert "529.982.247-25" not in body and "Maria Souza" not in body and "91234" not in body
    assert sent["messages"][1]["content"][0]["text"] == "Sou a [PESSOA_1], CPF [CPF_1], telefone [TELEFONE_1]."
    assert json.loads(sent["messages"][2]["tool_calls"][0]["function"]["arguments"]) == {"cpf": "[CPF_1]"}
    assert sent["messages"][3]["content"] == "Cliente [PESSOA_1] encontrada."
    assert "marcadores" in sent["messages"][0]["content"] and sent["messages"][0]["content"].startswith("Você é")
    assert prepared.counts == {"PESSOA": 2, "CPF": 2, "TELEFONE": 1}


def test_no_instruction_when_nothing_was_hidden():
    _, _, sent = prepare("/v1/chat/completions", {"messages": [{"role": "user", "content": "Bom dia!"}]})
    assert sent["messages"] == [{"role": "user", "content": "Bom dia!"}]


def test_block_policy():
    with pytest.raises(BlockedError) as error:
        prepare("/v1/chat/completions", {"messages": [{"role": "user", "content": "cartão 4111 1111 1111 1111"}]},
                block=("CARTAO_CREDITO",))
    assert error.value.labels == ["CARTAO_CREDITO"]


def test_openai_chat_non_stream_restore():
    gateway, prepared, _ = prepare("/v1/chat/completions", {"messages": [{"role": "user", "content": PII}]})
    response = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "Olá [PESSOA_1]!",
                "tool_calls": [{"function": {"name": "f", "arguments": '{"cpf": "[CPF_1]"}'}}]}}]}
    restored = json.loads(gateway.restore_body(prepared, json.dumps(response).encode()))
    message = restored["choices"][0]["message"]
    assert message["content"] == "Olá Maria Souza!"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"cpf": "529.982.247-25"}


@pytest.mark.parametrize("seed", range(5))
def test_openai_chat_stream_with_tool_calls(seed):
    gateway, prepared, _ = prepare("/v1/chat/completions", {"stream": True, "messages": [{"role": "user", "content": PII}]})
    pieces = ["Olá [PES", "SOA_1], seu CPF é [CP", "F_1]. Ligaremos no TELEF", "ONE_1 ção"]
    events = [(None, {"id": "c", "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]}) for p in pieces]
    events += [(None, {"id": "c", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": a}}]},
                                              "finish_reason": None}]}) for a in ['{"cpf": "[CPF', '_1]"}']]
    events += [(None, {"id": "c", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}), (None, "[DONE]")]
    output = run_stream(gateway, prepared, events, seed)
    text = "".join(e[1]["choices"][0]["delta"].get("content") or "" for e in output if isinstance(e[1], dict) and e[1].get("choices"))
    arguments = "".join(
        call["function"]["arguments"] for e in output if isinstance(e[1], dict) and e[1].get("choices")
        for call in e[1]["choices"][0]["delta"].get("tool_calls") or []
    )
    assert text == "Olá Maria Souza, seu CPF é 529.982.247-25. Ligaremos no (11) 91234-5678 ção"
    assert json.loads(arguments) == {"cpf": "529.982.247-25"}
    assert output[-1] == (None, "[DONE]")


@pytest.mark.parametrize("seed", range(5))
def test_anthropic_stream(seed):
    gateway, prepared, sent = prepare("/v1/messages", {"stream": True, "system": "Atendente.", "messages": [
        {"role": "user", "content": [{"type": "text", "text": PII}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "Maria Souza", "signature": "abc"}]},
    ]})
    assert sent["system"].startswith("Atendente.") and "marcadores" in sent["system"]
    assert sent["messages"][1]["content"][0]["thinking"] == "Maria Souza"  # bloco assinado fica intacto
    events = [
        ("message_start", {"type": "message_start", "message": {"id": "m", "content": []}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Prezada [PESSOA"}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "_1], CPF [CPF_1"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_stop", {"type": "message_stop"}),
    ]
    output = run_stream(gateway, prepared, events, seed)
    text = "".join(d["delta"]["text"] for n, d in output if n == "content_block_delta")
    assert text == "Prezada Maria Souza, CPF 529.982.247-25"
    assert [n for n, _ in output][-2:] == ["content_block_stop", "message_stop"]


@pytest.mark.parametrize("seed", range(3))
def test_responses_api_stream(seed):
    gateway, prepared, sent = prepare("/v1/responses", {"stream": True, "instructions": "Seja breve.", "input": PII})
    assert sent["input"] == "Sou a [PESSOA_1], CPF [CPF_1], telefone [TELEFONE_1]."
    events = [
        ("response.output_text.delta", {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": "Oi [PESSOA"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": "_1]"}),
        ("response.output_text.done", {"type": "response.output_text.done", "output_index": 0, "content_index": 0, "text": "Oi [PESSOA_1]"}),
        ("response.completed", {"type": "response.completed", "response": {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Oi [PESSOA_1]"}]}]}}),
    ]
    output = run_stream(gateway, prepared, events, seed)
    deltas = "".join(d["delta"] for n, d in output if n == "response.output_text.delta")
    assert deltas == "Oi Maria Souza"
    done = next(d for n, d in output if n == "response.output_text.done")
    assert done["text"] == "Oi Maria Souza"
    completed = next(d for n, d in output if n == "response.completed")
    assert completed["response"]["output"][0]["content"][0]["text"] == "Oi Maria Souza"


@pytest.mark.parametrize("seed", range(3))
def test_gemini_stream_and_masking(seed):
    path = "/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
    gateway, prepared, sent = prepare(path, {
        "systemInstruction": {"parts": [{"text": "Responda em português."}]},
        "contents": [{"role": "user", "parts": [{"text": PII}]}],
    })
    assert prepared.stream
    assert sent["contents"][0]["parts"][0]["text"] == "Sou a [PESSOA_1], CPF [CPF_1], telefone [TELEFONE_1]."
    assert len(sent["systemInstruction"]["parts"]) == 2
    events = [
        (None, {"candidates": [{"index": 0, "content": {"role": "model", "parts": [{"text": "Olá [PES"}]}}]}),
        (None, {"candidates": [{"index": 0, "content": {"role": "model", "parts": [{"text": "SOA_1], CPF CPF_1"}]},
                                "finishReason": "STOP"}]}),
    ]
    output = run_stream(gateway, prepared, events, seed)
    text = "".join(d["candidates"][0]["content"]["parts"][0]["text"] for _, d in output)
    assert text == "Olá Maria Souza, CPF 529.982.247-25"


def test_embeddings_are_masked_and_output_not_touched():
    gateway, prepared, sent = prepare("/v1/embeddings", {"input": [PII, "sem dados"]})
    assert sent["input"] == ["Sou a [PESSOA_1], CPF [CPF_1], telefone [TELEFONE_1].", "sem dados"]
    body = json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode()
    assert gateway.restore_body(prepared, body) == body


def test_anthropic_text_documents_and_tool_results_are_masked():
    _, _, sent = prepare("/v1/messages", {"messages": [{"role": "user", "content": [
        {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": PII}},
        {"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "CPF 529.982.247-25"}]},
    ]}]})
    blocks = sent["messages"][0]["content"]
    assert "[CPF_1]" in blocks[0]["source"]["data"]
    assert blocks[1]["content"][0]["text"] == "CPF [CPF_1]"


def test_sse_comments_and_crlf_are_preserved():
    gateway, prepared, _ = prepare("/v1/chat/completions", {"stream": True, "messages": [{"role": "user", "content": PII}]})
    transformer = gateway.stream(prepared)
    raw = b": OPENROUTER PROCESSING\r\n\r\ndata: {\"choices\":[{\"index\":0,\"delta\":{\"content\":\"[CPF_1]\"},\"finish_reason\":\"stop\"}]}\r\n\r\n"
    output = (transformer.feed(raw[:30]) + transformer.feed(raw[30:]) + transformer.close()).decode()
    assert output.startswith(": OPENROUTER PROCESSING\n\n")
    assert "529.982.247-25" in output
