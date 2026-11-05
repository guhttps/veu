"""Leitura e reescrita incremental de Server-Sent Events (respostas em streaming)."""

from __future__ import annotations

import codecs
import json
from collections.abc import Callable
from typing import Any

Event = tuple[str | None, Any]


def encode_event(name: str | None, data: Any, extra_lines: list[str] | None = None) -> str:
    lines = list(extra_lines or [])
    if name:
        lines.append(f"event: {name}")
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines.extend(f"data: {line}" for line in payload.split("\n"))
    return "\n".join(lines) + "\n\n"


class NDJSONTransformer:
    """Mesmo papel do SSETransformer para streams de JSON por linha (API nativa do Ollama)."""

    def __init__(self, process: Callable[[str | None, Any], list[Event]], finish: Callable[[], list[Event]]):
        self._process = process
        self._finish = finish
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""

    def feed(self, chunk: bytes) -> bytes:
        self._buffer += self._decoder.decode(chunk)
        lines = self._buffer.split("\n")
        self._buffer = lines.pop()
        return "".join(self._handle(line) for line in lines).encode()

    def close(self) -> bytes:
        self._buffer += self._decoder.decode(b"", final=True)
        output = self._handle(self._buffer) if self._buffer.strip() else ""
        self._buffer = ""
        output += "".join(self._encode(data) for _, data in self._finish())
        return output.encode()

    @staticmethod
    def _encode(data: Any) -> str:
        return (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, separators=(",", ":"))) + "\n"

    def _handle(self, line: str) -> str:
        line = line.rstrip("\r")
        if not line.strip():
            return line + "\n"
        try:
            data: Any = json.loads(line)
        except ValueError:
            return line + "\n"
        return "".join(self._encode(event_data) for _, event_data in self._process(None, data))


class SSETransformer:
    """Recebe bytes de um stream SSE e devolve bytes com os eventos transformados.

    process(nome, dados) devolve a lista de eventos a emitir no lugar do evento recebido
    (os dados são o JSON já decodificado, ou o texto original se não for JSON, como "[DONE]").
    finish() devolve eventos finais quando o stream termina.
    """

    def __init__(self, process: Callable[[str | None, Any], list[Event]], finish: Callable[[], list[Event]]):
        self._process = process
        self._finish = finish
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""
        self._pending_cr = False

    def feed(self, chunk: bytes) -> bytes:
        text = self._decoder.decode(chunk)
        if self._pending_cr:
            text = "\r" + text
            self._pending_cr = False
        if text.endswith("\r"):
            text, self._pending_cr = text[:-1], True
        self._buffer += text.replace("\r\n", "\n").replace("\r", "\n")
        output = []
        while True:
            index = self._buffer.find("\n\n")
            if index == -1:
                break
            block, self._buffer = self._buffer[:index], self._buffer[index + 2:]
            output.append(self._handle(block))
        return "".join(output).encode()

    def close(self) -> bytes:
        tail = self._decoder.decode(b"", final=True)
        self._buffer += tail.replace("\r\n", "\n").replace("\r", "\n")
        output = []
        if self._buffer.strip():
            output.append(self._handle(self._buffer.strip("\n")))
        self._buffer = ""
        output.extend(encode_event(name, data) for name, data in self._finish())
        return "".join(output).encode()

    def _handle(self, block: str) -> str:
        name = None
        data_lines: list[str] = []
        extra: list[str] = []
        for line in block.split("\n"):
            if line.startswith(":") or not line:
                extra.append(line)
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                name = value
            elif field == "data":
                data_lines.append(value)
            else:
                extra.append(line)
        if not data_lines:
            return block + "\n\n"
        raw = "\n".join(data_lines)
        try:
            data: Any = json.loads(raw)
        except ValueError:
            data = raw
        events = self._process(name, data)
        if not events:
            return ""
        encoded = [encode_event(event_name, event_data) for event_name, event_data in events[:-1]]
        last_name, last_data = events[-1]
        encoded.append(encode_event(last_name, last_data, extra))
        return "".join(encoded)
