"""Camada que entende os formatos das APIs de IA (OpenAI, Anthropic e Gemini)."""

from veu.gateway.adapters import ADAPTERS, Adapter, Masker, StreamState, detect_adapter, restore_obj
from veu.gateway.pipeline import INSTRUCTION, BlockedError, Gateway, Prepared
from veu.gateway.sse import SSETransformer

__all__ = [
    "ADAPTERS",
    "INSTRUCTION",
    "Adapter",
    "BlockedError",
    "Gateway",
    "Masker",
    "Prepared",
    "SSETransformer",
    "StreamState",
    "detect_adapter",
    "restore_obj",
]
