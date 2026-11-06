"""Guardrail do LiteLLM: esconde antes da chamada e restaura a resposta, inclusive em streaming."""

import asyncio

import pytest

litellm = pytest.importorskip("litellm")

from litellm.types.utils import (  # noqa: E402
    ChatCompletionMessageToolCall,
    Delta,
    Function,
    Message,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)

from veu import Veu  # noqa: E402
from veu.config import Config  # noqa: E402
from veu.integrations.litellm import BlockedError, VeuGuardrail  # noqa: E402

CPF = "529.982.247-25"


def run(coroutine):
    return asyncio.run(coroutine)


def test_pre_call_masks_and_post_call_restores():
    guard = VeuGuardrail(guardrail_name="veu", event_hook=["pre_call", "post_call"], default_on=True)
    data = {"model": "gpt", "messages": [{"role": "user", "content": f"Cliente Maria Souza, CPF {CPF}"}]}
    data = run(guard.async_pre_call_hook(None, None, data, "acompletion"))
    sent = str(data["messages"])
    assert CPF not in sent and "[CPF_1]" in sent and data["messages"][0]["role"] == "system"
    assert set(data["metadata"]) == {"veu_id"}  # nos metadados (que podem ir para logs) só um identificador

    response = ModelResponse(choices=[{"index": 0, "finish_reason": "stop", "message": Message(
        content="Olá [PESSOA_1], CPF [CPF_1]",
        tool_calls=[ChatCompletionMessageToolCall(id="c1", type="function", function=Function(
            name="buscar", arguments='{"cpf": "[CPF_1]"}'))],
    )}])
    run(guard.async_post_call_success_hook(data, None, response))
    message = response.choices[0].message
    assert message.content == f"Olá Maria Souza, CPF {CPF}"
    assert CPF in message.tool_calls[0].function.arguments
    assert guard._vaults == {}


def test_streaming_with_split_placeholder():
    guard = VeuGuardrail()
    data = run(guard.async_pre_call_hook(None, None, {"messages": [{"role": "user", "content": f"CPF {CPF}"}]},
                                         "completion"))

    async def chunks():
        for text, finish in (("Seu CPF é [CP", None), ("F_1", None), ("].", "stop")):
            yield ModelResponseStream(choices=[StreamingChoices(index=0, delta=Delta(content=text), finish_reason=finish)])

    async def collect():
        return [chunk async for chunk in guard.async_post_call_streaming_iterator_hook(None, chunks(), data)]

    text = "".join(chunk.choices[0].delta.content or "" for chunk in run(collect()))
    assert text == f"Seu CPF é {CPF}."


def test_anthropic_messages_and_blocking():
    guard = VeuGuardrail(veu=Veu(Config(block=("CHAVE_PRIVADA",))))
    data = {"system": "Você é um assistente.", "messages": [{"role": "user", "content": [
        {"type": "text", "text": f"Paciente Maria Souza, CPF {CPF}"}]}]}
    data = run(guard.async_pre_call_hook(None, None, data, "aanthropic_messages"))
    assert CPF not in str(data) and "[CPF_1]" in data["messages"][0]["content"][0]["text"]
    response = {"content": [{"type": "thinking", "thinking": "[CPF_1]", "signature": "x"},
                            {"type": "text", "text": "Caso de [PESSOA_1]"}]}
    run(guard.async_post_call_success_hook(data, None, response))
    assert response["content"][1]["text"] == "Caso de Maria Souza"
    assert response["content"][0]["thinking"] == "[CPF_1]"  # bloco assinado não muda

    pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQ" + "A" * 60 + "\n-----END PRIVATE KEY-----"
    with pytest.raises((BlockedError, Exception), match="bloqueada"):
        run(guard.async_pre_call_hook(None, None, {"messages": [{"role": "user", "content": pem}]}, "acompletion"))


def test_other_call_types_pass_untouched():
    guard = VeuGuardrail()
    data = {"prompt": f"Desenhe Maria Souza {CPF}"}
    assert run(guard.async_pre_call_hook(None, None, dict(data), "aimage_generation")) == data
