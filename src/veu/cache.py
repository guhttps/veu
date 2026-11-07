"""Cache de detecção: agentes reenviam a conversa inteira a cada turno, e cada mensagem antiga seria analisada de novo.

O cache guarda só posições, tipos e pontuações, nunca o texto. A chave é um hash BLAKE2 com um sal aleatório
do processo, então ela não serve para confirmar se um texto passou pelo Véu. Fica só na memória, some quando o
processo termina e só vale para textos longos (os curtos são baratos de analisar e fáceis de adivinhar).

No proxy, cada credencial de cliente tem o seu espaço no cache (cache_scope): um cliente não consegue, medindo o
tempo de resposta, descobrir se outro cliente mandou um texto.
"""

from __future__ import annotations

import contextvars
import hashlib
import os
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager

Spans = tuple[tuple[str, int, int, float, str], ...]

_scope: contextvars.ContextVar[str] = contextvars.ContextVar("veu_cache_scope", default="")


@contextmanager
def cache_scope(scope: str) -> Iterator[None]:
    """Separa o cache por cliente (por exemplo, o hash da credencial) enquanto o bloco roda."""
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)


class DetectionCache:
    """LRU em memória de resultados de detecção. max_entries=0 desliga."""

    def __init__(self, max_entries: int = 2048, min_chars: int = 256):
        self.max_entries = max_entries
        self.min_chars = min_chars
        self._salt = os.urandom(32)
        self._items: OrderedDict[bytes, Spans] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def usable(self, text: str) -> bool:
        return self.max_entries > 0 and len(text) >= self.min_chars

    def _key(self, text: str, extra: str) -> bytes:
        digest = hashlib.blake2b(key=self._salt, digest_size=16)
        digest.update(f"{_scope.get()}\0{extra}\0".encode())
        digest.update(text.encode("utf-8", "surrogatepass"))
        return digest.digest()

    def get(self, text: str, extra: str = "") -> Spans | None:
        key = self._key(text, extra)
        with self._lock:
            spans = self._items.get(key)
            if spans is None:
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return spans

    def put(self, text: str, spans: Spans, extra: str = "") -> None:
        key = self._key(text, extra)
        with self._lock:
            self._items[key] = spans
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
