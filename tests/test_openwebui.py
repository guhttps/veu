"""Filtro do Open WebUI: esconde na entrada, restaura no streaming e na saída, sem misturar conversas."""

import pytest

pytest.importorskip("pydantic")

from veu.integrations.openwebui import Filter  # noqa: E402

CPF = "529.982.247-25"


def chat(content, chat_id="c1"):
    return {"model": "m", "messages": [{"role": "user", "content": content}], "metadata": {"chat_id": chat_id}}


def test_inlet_masks_and_outlet_restores():
    veu_filter = Filter()
    body = veu_filter.inlet(chat(f"Sou Maria Souza, CPF {CPF}"), __metadata__={"chat_id": "c1"})
    assert body["messages"][0]["content"] == "Sou [PESSOA_1], CPF [CPF_1]"
    out = veu_filter.outlet({"messages": [{"role": "assistant", "content": "Olá [PESSOA_1] ([CPF_1])"}]},
                            __metadata__={"chat_id": "c1"})
    assert out["messages"][0]["content"] == f"Olá Maria Souza ({CPF})"


def test_stream_restores_split_placeholders():
    veu_filter = Filter()
    veu_filter.inlet(chat(f"CPF {CPF}"), __metadata__={"chat_id": "c1"})
    parts = ["Seu CPF é [CP", "F_1]."]
    output = ""
    for index, part in enumerate(parts):
        event = {"choices": [{"delta": {"content": part}, "finish_reason": "stop" if index == 1 else None}]}
        output += veu_filter.stream(event, __metadata__={"chat_id": "c1"})["choices"][0]["delta"]["content"]
    assert output == f"Seu CPF é {CPF}."


def test_stream_flushes_the_tail_into_an_empty_final_delta():
    # O último pedaço do streaming da OpenAI costuma ser {"delta": {}, "finish_reason": "stop"}.
    veu_filter = Filter()
    veu_filter.inlet(chat(f"CPF {CPF}"), __metadata__={"chat_id": "c1"})
    events = [{"choices": [{"delta": {"content": "Seu CPF é CPF_"}, "finish_reason": None}]},
              {"choices": [{"delta": {}, "finish_reason": "stop"}]}]
    output = "".join(veu_filter.stream(event, __metadata__={"chat_id": "c1"})["choices"][0]["delta"].get("content", "")
                     for event in events)
    assert output == "Seu CPF é CPF_"  # o pedaço retido ("CPF_" podia virar um marcador) volta no fim


def test_conversations_never_share_vaults():
    veu_filter = Filter()
    veu_filter.inlet(chat(f"CPF {CPF}", "a"), __metadata__={"chat_id": "a"})
    veu_filter.inlet(chat("oi", "b"), __metadata__={"chat_id": "b"})
    out = veu_filter.outlet({"messages": [{"role": "assistant", "content": "[CPF_1]"}]}, __metadata__={"chat_id": "b"})
    assert out["messages"][0]["content"] == "[CPF_1]"
    # Pedaço de streaming sem conversa: nunca é restaurado.
    event = {"choices": [{"delta": {"content": "[CPF_1]"}, "finish_reason": "stop"}]}
    assert veu_filter.stream(event)["choices"][0]["delta"]["content"] == "[CPF_1]"


def test_blocked_types_refuse_the_message():
    veu_filter = Filter()
    key = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"
    with pytest.raises(ValueError, match="CHAVE_PRIVADA"):
        veu_filter.inlet(chat(f"minha chave {key}"), __metadata__={"chat_id": "c1"})


def test_example_file_exposes_the_filter():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "examples" / "open-webui" / "veu.py").read_text("utf-8")
    assert "requirements: veu" in source and "from veu.integrations.openwebui import Filter" in source
