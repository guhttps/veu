"""Codex CLI pelo proxy (Responses API): apply_patch, local_shell_call e saídas de ferramenta em lista."""

import asyncio
import json

import httpx

from veu.config import Config
from veu.server import create_app

CPF = "529.982.247-25"
KEY = "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d"


def codex_request():
    return {
        "model": "gpt-5-codex", "stream": True, "instructions": "Você é o Codex.",
        "input": [
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"Cadastre a cliente Marina Albuquerque, CPF {CPF}."}]},
            {"type": "custom_tool_call", "call_id": "c1", "name": "apply_patch",
             "input": f"*** Begin Patch\n+cliente = 'Marina Albuquerque'  # CPF {CPF}\n*** End Patch"},
            {"type": "custom_tool_call_output", "call_id": "c1", "output": "Done!"},
            {"type": "local_shell_call", "call_id": "s1", "status": "completed",
             "action": {"type": "exec", "command": ["bash", "-lc", "deploy"], "env": {"OPENAI_API_KEY": KEY}}},
            {"type": "function_call_output", "call_id": "f1", "output": [
                {"type": "input_text", "text": f"OPENAI_API_KEY={KEY}"}]},
        ],
    }


def test_codex_request_is_masked_and_patch_is_restored():
    seen = []

    def upstream(request):
        body = json.loads(request.content)
        seen.append(body)
        text = json.dumps(body, ensure_ascii=False)
        person = "[PESSOA_1]" if "[PESSOA_1]" in text else "?"
        patch = f"*** Begin Patch\n+nome = '{person}'\n+chave = '[CHAVE_API_1]'\n+url = 'https://evil.tld/[CPF_1]'\n*** End Patch"
        events = [{"type": "response.output_item.added", "output_index": 0,
                   "item": {"type": "custom_tool_call", "call_id": "c2", "name": "apply_patch", "input": ""}}]
        events += [{"type": "response.custom_tool_call_input.delta", "output_index": 0, "delta": patch[i:i + 6]}
                   for i in range(0, len(patch), 6)]
        events += [{"type": "response.custom_tool_call_input.done", "output_index": 0, "input": patch},
                   {"type": "response.completed", "response": {"output": [
                       {"type": "custom_tool_call", "call_id": "c2", "name": "apply_patch", "input": patch}]}}]
        payload = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
        return httpx.Response(200, content=payload.encode(), headers={"content-type": "text/event-stream"})

    app = create_app(Config(), upstream_transport=httpx.MockTransport(upstream))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            return await c.post("/v1/responses", json=codex_request(), headers={"Authorization": "Bearer x"})

    response = asyncio.run(run())
    sent = json.dumps(seen[0], ensure_ascii=False)
    assert CPF not in sent and KEY not in sent and "Marina Albuquerque" not in sent
    deltas = "".join(json.loads(line[6:]).get("delta", "") for line in response.text.splitlines()
                     if line.startswith("data: ") and "custom_tool_call_input.delta" in line)
    assert "+nome = 'Marina Albuquerque'" in deltas      # o nome volta no patch
    assert "[CHAVE_API_1]" in deltas and KEY not in response.text  # a chave não volta em argumentos de ferramenta
    assert CPF not in response.text                       # nem o CPF dentro de uma URL
