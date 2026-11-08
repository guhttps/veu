"""Adaptadores para os formatos das APIs de IA.

Cada adaptador sabe onde estão os textos de uma requisição (para esconder os dados pessoais) e
onde estão os textos da resposta, inclusive em streaming (para restaurar os dados reais).
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any

from veu.anonymizer import Anonymizer
from veu.gateway.sse import Event
from veu.vault import StreamRestorer, Vault

# Blocos assinados ou criptografados pelo provedor: alterar o texto invalidaria a assinatura.
_UNTOUCHED_TYPES = frozenset({"thinking", "redacted_thinking"})
_UNTOUCHED_KEYS = frozenset({"encrypted_content", "signature"})


class Masker:
    """Esconde os dados pessoais de todos os textos de uma requisição usando um único cofre."""

    def __init__(self, anonymizer: Anonymizer, vault: Vault, expand=None):
        self.anonymizer = anonymizer
        self.vault = vault
        self.counts: Counter[str] = Counter()
        # expand(texto) -> (texto, conhecidos): acrescenta o conteúdo de links permitidos (Notion, Google) e informa
        # os dados pessoais que a fonte já marcou, para esconder antes da detecção.
        self.expand = expand
        self._in_arguments = False

    def text(self, value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        known = None
        if self.expand is not None and not self._in_arguments:
            value, known = self.expand(value)
        # Marcadores que já vêm no texto são desarmados antes de o Véu inserir os seus.
        value = self.vault.neutralize(value)
        if known:
            from veu.sources import replace_known

            value = replace_known(value, known, self.anonymizer, self.vault, self.counts)
        result = self.anonymizer.anonymize(value, self.vault, neutralize=False)
        self.counts.update(result.counts())
        return result.text

    def json_string(self, value: Any) -> Any:
        """Argumentos de ferramentas chegam como texto JSON: esconde os valores sem quebrar o JSON."""
        if not isinstance(value, str) or not value:
            return value
        try:
            parsed = json.loads(value)
        except ValueError:
            return self.text(value)
        self._in_arguments = True  # argumentos de ferramentas não ganham conteúdo de links
        try:
            return json.dumps(self.obj(parsed), ensure_ascii=False)
        finally:
            self._in_arguments = False

    def obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.obj(item) for item in value)
        if isinstance(value, dict):
            return {key: self.obj(item) for key, item in value.items()}
        return value


# Onde ficam os argumentos de chamadas de ferramenta nas respostas (OpenAI, Responses, Anthropic, Gemini, Ollama).
_TOOL_KEYS = frozenset({"arguments", "partial_json", "args", "functionCall", "function_call", "tool_calls"})
_TOOL_TYPES = frozenset({"tool_use", "server_tool_use", "function_call", "custom_tool_call", "local_shell_call",
                         "response.custom_tool_call_input.done", "response.function_call_arguments.done"})


def restore_obj(value: Any, vault: Vault, *, tool: bool = False) -> Any:
    """Restaura todos os textos de uma resposta JSON. tool: o valor é argumento de uma chamada de ferramenta."""
    if isinstance(value, str):
        return vault.restore(value, tool=tool)
    if isinstance(value, list):
        return [restore_obj(item, vault, tool=tool) for item in value]
    if isinstance(value, tuple):
        return tuple(restore_obj(item, vault, tool=tool) for item in value)
    if isinstance(value, dict):
        if value.get("type") in _UNTOUCHED_TYPES:
            return value
        call = value.get("type") in _TOOL_TYPES
        restored = {}
        for key, item in value.items():
            in_tool = tool or key in _TOOL_KEYS or (call and key in ("input", "arguments"))
            if key in _UNTOUCHED_KEYS:
                restored[key] = item
            elif key in ("arguments", "partial_json") and isinstance(item, str):
                restored[key] = restore_json_string(item, vault)
            else:
                restored[key] = restore_obj(item, vault, tool=in_tool)
        return restored
    return value


def restore_json_string(value: str, vault: Vault, *, tool: bool = True) -> str:
    """Argumentos de ferramenta em texto JSON: restaura os valores sem quebrar o JSON."""
    try:
        parsed = json.loads(value)
    except ValueError:
        return vault.restore(value, json_escape=True, tool=tool)
    return json.dumps(restore_obj(parsed, vault, tool=tool), ensure_ascii=False)


class StreamState:
    """Um restaurador por campo de texto do stream (cada escolha, bloco ou argumento de ferramenta)."""

    def __init__(self, vault: Vault):
        self.vault = vault
        self._restorers: dict[tuple, StreamRestorer] = {}
        self.meta: dict[str, Any] = {}

    def feed(self, key: tuple, text: str, *, json_escape: bool = False, tool: bool | None = None) -> str:
        """tool: o texto é argumento de ferramenta (padrão: o mesmo que json_escape)."""
        restorer = self._restorers.get(key)
        if restorer is None:
            restorer = self._restorers[key] = self.vault.restorer(json_escape=json_escape, tool=tool)
        return restorer.feed(text)

    def flush(self, key: tuple) -> str:
        restorer = self._restorers.pop(key, None)
        return restorer.flush() if restorer else ""

    def pending_keys(self) -> list[tuple]:
        """Campos com texto retido esperando o próximo pedaço."""
        return [key for key, restorer in self._restorers.items() if restorer.pending]

    def restore(self, value: Any) -> Any:
        return restore_obj(value, self.vault)


class Adapter:
    name = ""
    restores_output = True

    def matches(self, method: str, path: str) -> bool:
        raise NotImplementedError

    def mask(self, payload: dict, masker: Masker) -> None:
        raise NotImplementedError

    def instruct(self, payload: dict, instruction: str) -> None:
        pass

    def is_stream(self, payload: dict, path: str) -> bool:
        return payload.get("stream") is True

    def error_body(self, message: str) -> dict:
        return {"error": {"message": message, "type": "veu_bloqueado", "code": "dados_pessoais_bloqueados"}}

    def stream_event(self, name: str | None, data: Any, state: StreamState) -> list[Event]:
        return [(name, state.restore(data))]

    def stream_finish(self, state: StreamState) -> list[Event]:
        return []


def _mask_content(content: Any, masker: Masker) -> Any:
    """Conteúdo no formato OpenAI: texto ou lista de partes ({"type": "text", "text": ...})."""
    if isinstance(content, str):
        return masker.text(content)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text"):
                part["text"] = masker.text(part.get("text"))
    return content


class OpenAIChatAdapter(Adapter):
    """POST /v1/chat/completions (OpenAI e todas as APIs compatíveis)."""

    name = "openai-chat"

    def matches(self, method, path):
        return method == "POST" and path.rstrip("/").endswith("/chat/completions")

    def mask(self, payload, masker):
        for message in payload.get("messages") or []:
            if not isinstance(message, dict):
                continue
            message["content"] = _mask_content(message.get("content"), masker)
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if isinstance(function, dict):
                    function["arguments"] = masker.json_string(function.get("arguments"))
            if isinstance(message.get("function_call"), dict):
                message["function_call"]["arguments"] = masker.json_string(message["function_call"].get("arguments"))

    def instruct(self, payload, instruction):
        messages = payload.setdefault("messages", [])
        first = messages[0] if messages else None
        if isinstance(first, dict) and first.get("role") in ("system", "developer") and isinstance(first.get("content"), str):
            first["content"] = f"{first['content']}\n\n{instruction}"
        else:
            messages.insert(0, {"role": "system", "content": instruction})

    def stream_event(self, name, data, state):
        if data == "[DONE]":
            return [*self.stream_finish(state), (name, data)]
        if not isinstance(data, dict):
            return [(name, data)]
        state.meta["template"] = {key: data[key] for key in ("id", "object", "created", "model") if key in data}
        for choice in data.get("choices") or []:
            index = choice.get("index", 0)
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue
            for field in ("content", "reasoning_content", "reasoning", "refusal"):
                if isinstance(delta.get(field), str):
                    delta[field] = state.feed(("c", index, field), delta[field])
            for call in delta.get("tool_calls") or []:
                function = call.get("function") or {}
                if isinstance(function.get("arguments"), str):
                    function["arguments"] = state.feed(("t", index, call.get("index", 0)), function["arguments"],
                                                       json_escape=True)
            if choice.get("finish_reason"):
                self._flush_choice(index, delta, state)
        return [(name, data)]

    def _flush_choice(self, index: int, delta: dict, state: StreamState) -> None:
        for key in state.pending_keys():
            if key[1] != index:
                continue
            text = state.flush(key)
            if not text:
                continue
            if key[0] == "c":
                delta[key[2]] = (delta.get(key[2]) or "") + text
            else:
                calls = delta.setdefault("tool_calls", [])
                call = next((c for c in calls if c.get("index", 0) == key[2]), None)
                if call is None:
                    call = {"index": key[2], "function": {"arguments": ""}}
                    calls.append(call)
                function = call.setdefault("function", {})
                function["arguments"] = (function.get("arguments") or "") + text

    def stream_finish(self, state):
        if not state.pending_keys():
            return []
        chunk = dict(state.meta.get("template") or {"object": "chat.completion.chunk"})
        choices: dict[int, dict] = {}
        for key in state.pending_keys():
            choices.setdefault(key[1], {"index": key[1], "delta": {}, "finish_reason": None})
        for index, choice in choices.items():
            self._flush_choice(index, choice["delta"], state)
        chunk["choices"] = list(choices.values())
        return [(None, chunk)]


class OpenAICompletionsAdapter(Adapter):
    """POST /v1/completions (API legada de completions)."""

    name = "openai-completions"

    def matches(self, method, path):
        path = path.rstrip("/")
        return method == "POST" and path.endswith("/completions") and not path.endswith("/chat/completions")

    def mask(self, payload, masker):
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            payload["prompt"] = masker.text(prompt)
        elif isinstance(prompt, list) and all(isinstance(item, str) for item in prompt):
            payload["prompt"] = [masker.text(item) for item in prompt]

    def stream_event(self, name, data, state):
        if data == "[DONE]":
            return [*self.stream_finish(state), (name, data)]
        if not isinstance(data, dict):
            return [(name, data)]
        state.meta["template"] = {key: data[key] for key in ("id", "object", "created", "model") if key in data}
        for choice in data.get("choices") or []:
            index = choice.get("index", 0)
            if isinstance(choice.get("text"), str):
                choice["text"] = state.feed(("c", index), choice["text"])
            if choice.get("finish_reason"):
                choice["text"] = (choice.get("text") or "") + state.flush(("c", index))
        return [(name, data)]

    def stream_finish(self, state):
        if not state.pending_keys():
            return []
        chunk = dict(state.meta.get("template") or {"object": "text_completion"})
        chunk["choices"] = [{"index": key[1], "text": state.flush(key), "finish_reason": None} for key in state.pending_keys()]
        return [(None, chunk)]


class OpenAIEmbeddingsAdapter(Adapter):
    """POST /v1/embeddings: só esconde os dados do texto de entrada."""

    name = "openai-embeddings"
    restores_output = False

    def matches(self, method, path):
        return method == "POST" and path.rstrip("/").endswith("/embeddings")

    def mask(self, payload, masker):
        value = payload.get("input")
        if isinstance(value, str):
            payload["input"] = masker.text(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            payload["input"] = [masker.text(item) for item in value]


class OpenAIResponsesAdapter(Adapter):
    """POST /v1/responses (API Responses da OpenAI)."""

    name = "openai-responses"

    def matches(self, method, path):
        return method == "POST" and path.rstrip("/").endswith("/responses")

    def mask(self, payload, masker):
        if isinstance(payload.get("instructions"), str):
            payload["instructions"] = masker.text(payload["instructions"])
        value = payload.get("input")
        if isinstance(value, str):
            payload["input"] = masker.text(value)
            return
        for item in value or []:
            if not isinstance(item, dict) or item.get("type") == "reasoning":
                continue
            if "content" in item:
                item["content"] = _mask_content(item.get("content"), masker)
            kind = item.get("type")
            if kind == "function_call":
                item["arguments"] = masker.json_string(item.get("arguments"))
            elif kind in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
                item["output"] = _mask_content(item.get("output"), masker)
            elif kind == "custom_tool_call":  # ferramentas de texto livre, como o apply_patch do Codex
                item["input"] = masker.text(item.get("input"))
            elif kind == "local_shell_call" and isinstance(item.get("action"), dict):
                item["action"] = masker.obj(item["action"])

    def instruct(self, payload, instruction):
        current = payload.get("instructions")
        payload["instructions"] = f"{current}\n\n{instruction}" if isinstance(current, str) and current else instruction

    def stream_event(self, name, data, state):
        if not isinstance(data, dict):
            return [(name, data)]
        kind = data.get("type")
        if kind == "response.output_text.delta":
            key = ("o", data.get("output_index", 0), data.get("content_index", 0))
            data["delta"] = state.feed(key, data.get("delta") or "")
            return [(name, data)]
        if kind == "response.function_call_arguments.delta":
            key = ("f", data.get("output_index", 0))
            data["delta"] = state.feed(key, data.get("delta") or "", json_escape=True)
            return [(name, data)]
        if kind == "response.custom_tool_call_input.delta":
            key = ("c", data.get("output_index", 0))
            data["delta"] = state.feed(key, data.get("delta") or "", tool=True)
            return [(name, data)]
        if kind in ("response.output_text.done", "response.function_call_arguments.done",
                    "response.custom_tool_call_input.done"):
            if kind == "response.output_text.done":
                key = ("o", data.get("output_index", 0), data.get("content_index", 0))
                delta_kind = "response.output_text.delta"
            elif kind == "response.custom_tool_call_input.done":
                key = ("c", data.get("output_index", 0))
                delta_kind = "response.custom_tool_call_input.delta"
            else:
                key = ("f", data.get("output_index", 0))
                delta_kind = "response.function_call_arguments.delta"
            events: list[Event] = []
            tail = state.flush(key)
            if tail:
                extra = {k: data[k] for k in ("item_id", "output_index", "content_index") if k in data}
                event_name = delta_kind if name else None
                events.append((event_name, {"type": delta_kind, **extra, "delta": tail}))
            events.append((name, state.restore(data)))
            return events
        if kind and "reasoning" in kind:
            return [(name, data)]
        return [(name, state.restore(data))]

    def stream_finish(self, state):
        events = []
        for key in state.pending_keys():
            tail = state.flush(key)
            if not tail:
                continue
            if key[0] == "o":
                events.append((None, {"type": "response.output_text.delta", "output_index": key[1],
                                      "content_index": key[2], "delta": tail}))
            elif key[0] == "c":
                events.append((None, {"type": "response.custom_tool_call_input.delta", "output_index": key[1],
                                      "delta": tail}))
            else:
                events.append((None, {"type": "response.function_call_arguments.delta", "output_index": key[1],
                                      "delta": tail}))
        return events


class AnthropicMessagesAdapter(Adapter):
    """POST /v1/messages e /v1/messages/count_tokens (Anthropic)."""

    name = "anthropic-messages"

    def matches(self, method, path):
        path = path.rstrip("/")
        return method == "POST" and (path.endswith("/messages") or path.endswith("/messages/count_tokens"))

    def _mask_blocks(self, blocks: Any, masker: Masker) -> Any:
        if isinstance(blocks, str):
            return masker.text(blocks)
        if not isinstance(blocks, list):
            return blocks
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") in _UNTOUCHED_TYPES:
                continue
            kind = block.get("type")
            if kind == "text":
                block["text"] = masker.text(block.get("text"))
            elif kind in ("tool_use", "server_tool_use"):
                block["input"] = masker.obj(block.get("input"))
            elif kind == "tool_result":
                block["content"] = self._mask_blocks(block.get("content"), masker)
            elif kind == "document":
                source = block.get("source")
                if isinstance(source, dict) and source.get("type") == "text":
                    source["data"] = masker.text(source.get("data"))
                elif isinstance(source, dict) and source.get("type") == "content":
                    source["content"] = self._mask_blocks(source.get("content"), masker)
        return blocks

    def mask(self, payload, masker):
        if "system" in payload:
            payload["system"] = self._mask_blocks(payload["system"], masker)
        for message in payload.get("messages") or []:
            if isinstance(message, dict):
                message["content"] = self._mask_blocks(message.get("content"), masker)

    def instruct(self, payload, instruction):
        system = payload.get("system")
        if isinstance(system, list):
            system.append({"type": "text", "text": instruction})
        elif isinstance(system, str) and system:
            payload["system"] = f"{system}\n\n{instruction}"
        else:
            payload["system"] = instruction

    def error_body(self, message):
        return {"type": "error", "error": {"type": "invalid_request_error", "message": message}}

    def stream_event(self, name, data, state):
        if not isinstance(data, dict):
            return [(name, data)]
        kind = data.get("type")
        if kind == "content_block_start":
            return [(name, state.restore(data))]
        if kind == "content_block_delta":
            index = data.get("index", 0)
            delta = data.get("delta") or {}
            if delta.get("type") == "text_delta":
                delta["text"] = state.feed(("b", index, "text_delta"), delta.get("text") or "")
            elif delta.get("type") == "input_json_delta":
                delta["partial_json"] = state.feed(("b", index, "input_json_delta"), delta.get("partial_json") or "",
                                                   json_escape=True)
            return [(name, data)]
        if kind == "content_block_stop":
            index = data.get("index", 0)
            events = self._flush_block(index, state, with_names=name is not None)
            return [*events, (name, data)]
        if kind == "message_stop":
            events = []
            for key in state.pending_keys():
                events.extend(self._flush_block(key[1], state, with_names=name is not None))
            return [*events, (name, data)]
        return [(name, state.restore(data))]

    def _flush_block(self, index: int, state: StreamState, with_names: bool) -> list[Event]:
        events = []
        for key in state.pending_keys():
            if key[1] != index:
                continue
            tail = state.flush(key)
            if tail:
                field = "text" if key[2] == "text_delta" else "partial_json"
                event = {"type": "content_block_delta", "index": index, "delta": {"type": key[2], field: tail}}
                events.append(("content_block_delta" if with_names else None, event))
        return events

    def stream_finish(self, state):
        events = []
        for key in state.pending_keys():
            events.extend(self._flush_block(key[1], state, with_names=True))
        return events


class GeminiAdapter(Adapter):
    """API nativa do Gemini: generateContent, streamGenerateContent, countTokens e embedContent."""

    name = "gemini"

    _METHODS = (":generateContent", ":streamGenerateContent", ":countTokens", ":embedContent", ":batchEmbedContents")

    def matches(self, method, path):
        return method == "POST" and any(path.rstrip("/").endswith(suffix) for suffix in self._METHODS)

    def is_stream(self, payload, path):
        return ":streamGenerateContent" in path

    def _mask_content(self, content: Any, masker: Masker) -> None:
        if not isinstance(content, dict):
            return
        for part in content.get("parts") or []:
            if not isinstance(part, dict) or part.get("thought"):
                continue
            if isinstance(part.get("text"), str):
                part["text"] = masker.text(part["text"])
            for key in ("functionCall", "function_call"):
                if isinstance(part.get(key), dict):
                    part[key]["args"] = masker.obj(part[key].get("args"))
            for key in ("functionResponse", "function_response"):
                if isinstance(part.get(key), dict):
                    part[key]["response"] = masker.obj(part[key].get("response"))

    def mask(self, payload, masker):
        for content in payload.get("contents") or []:
            self._mask_content(content, masker)
        for key in ("systemInstruction", "system_instruction", "content"):
            self._mask_content(payload.get(key), masker)
        for request in payload.get("requests") or []:
            if isinstance(request, dict):
                self._mask_content(request.get("content"), masker)
        generate = payload.get("generateContentRequest")
        if isinstance(generate, dict):
            self.mask(generate, masker)

    def instruct(self, payload, instruction):
        if "contents" not in payload:
            return
        key = "system_instruction" if "system_instruction" in payload else "systemInstruction"
        system = payload.get(key)
        if not isinstance(system, dict):
            system = payload[key] = {"parts": []}
        system.setdefault("parts", []).append({"text": instruction})

    def error_body(self, message):
        return {"error": {"code": 400, "message": message, "status": "INVALID_ARGUMENT"}}

    def stream_event(self, name, data, state):
        if not isinstance(data, dict):
            return [(name, data)]
        state.meta["template"] = {key: data[key] for key in ("modelVersion", "responseId") if key in data}
        for candidate in data.get("candidates") or []:
            index = candidate.get("index", 0)
            content = candidate.get("content")
            last_text = None
            if isinstance(content, dict):
                for part in content.get("parts") or []:
                    if not isinstance(part, dict) or part.get("thought"):
                        continue
                    if isinstance(part.get("text"), str):
                        part["text"] = state.feed(("g", index), part["text"])
                        last_text = part
                    for key in ("functionCall", "function_call"):
                        if isinstance(part.get(key), dict):
                            part[key] = state.restore(part[key])
            if candidate.get("finishReason"):
                tail = state.flush(("g", index))
                if tail:
                    if last_text is None:
                        content = candidate.setdefault("content", {"role": "model", "parts": []})
                        last_text = {"text": ""}
                        content.setdefault("parts", []).append(last_text)
                    last_text["text"] += tail
        return [(name, data)]

    def stream_finish(self, state):
        if not state.pending_keys():
            return []
        template = copy.deepcopy(state.meta.get("template") or {})
        template["candidates"] = [
            {"index": key[1], "content": {"role": "model", "parts": [{"text": state.flush(key)}]}}
            for key in state.pending_keys()
        ]
        return [(None, template)]


class OllamaAdapter(Adapter):
    """API nativa do Ollama: /api/chat, /api/generate, /api/embed e /api/embeddings.

    O streaming é JSON por linha (NDJSON) e vem ligado por padrão quando "stream" não é informado.
    """

    name = "ollama"
    _PATHS = ("/api/chat", "/api/generate", "/api/embed", "/api/embeddings")

    def matches(self, method, path):
        return method == "POST" and any(path.rstrip("/").endswith(suffix) for suffix in self._PATHS)

    def is_stream(self, payload, path):
        return path.rstrip("/").endswith(("/api/chat", "/api/generate")) and payload.get("stream", True) is not False

    def mask(self, payload, masker):
        for message in payload.get("messages") or []:
            if isinstance(message, dict):
                message["content"] = masker.text(message.get("content"))
                for call in message.get("tool_calls") or []:
                    function = call.get("function") if isinstance(call, dict) else None
                    if isinstance(function, dict):
                        function["arguments"] = masker.obj(function.get("arguments"))
        for key in ("prompt", "system"):
            if isinstance(payload.get(key), str):
                payload[key] = masker.text(payload[key])
        value = payload.get("input")
        if isinstance(value, str):
            payload["input"] = masker.text(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            payload["input"] = [masker.text(item) for item in value]

    def instruct(self, payload, instruction):
        if "messages" in payload:
            messages = payload["messages"]
            if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
                messages[0]["content"] = f"{messages[0].get('content') or ''}\n\n{instruction}"
            else:
                messages.insert(0, {"role": "system", "content": instruction})
        elif "prompt" in payload:
            payload["system"] = f"{payload['system']}\n\n{instruction}" if payload.get("system") else instruction

    def error_body(self, message):
        return {"error": message}

    def stream_event(self, name, data, state):
        if not isinstance(data, dict):
            return [(name, data)]
        message = data.get("message")
        if isinstance(message, dict):
            if isinstance(message.get("content"), str):
                message["content"] = state.feed(("chat",), message["content"])
            if message.get("tool_calls"):
                message["tool_calls"] = state.restore(message["tool_calls"])
            if data.get("done"):
                message["content"] = (message.get("content") or "") + state.flush(("chat",))
        if isinstance(data.get("response"), str):
            data["response"] = state.feed(("generate",), data["response"])
            if data.get("done"):
                data["response"] += state.flush(("generate",))
        return [(name, data)]

    def stream_finish(self, state):
        events = []
        for key in state.pending_keys():
            tail = state.flush(key)
            if key == ("chat",):
                events.append((None, {"message": {"role": "assistant", "content": tail}, "done": False}))
            else:
                events.append((None, {"response": tail, "done": False}))
        return events


ADAPTERS: tuple[Adapter, ...] = (
    OpenAIChatAdapter(),
    OpenAIResponsesAdapter(),
    OpenAIEmbeddingsAdapter(),
    OpenAICompletionsAdapter(),
    AnthropicMessagesAdapter(),
    GeminiAdapter(),
    OllamaAdapter(),
)


def detect_adapter(method: str, path: str) -> Adapter | None:
    method = method.upper()
    path = path.split("?", 1)[0]
    for adapter in ADAPTERS:
        if adapter.matches(method, path):
            return adapter
    return None
