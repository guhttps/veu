"""Transporte do Véu para o httpx: LangChain, LlamaIndex, Groq, Mistral e SDKs mais antigos.

    import httpx
    from langchain_openai import ChatOpenAI
    from veu.integrations.httpx import VeuTransport

    modelo = ChatOpenAI(model="gpt-4o-mini", http_client=httpx.Client(transport=VeuTransport()))

Para os SDKs que usam o httpx2 (OpenAI 3.x, Anthropic 2.x), use veu.integrations.httpx2
ou os atalhos de veu.integrations.sdk.
"""

import httpx as _http

from veu.integrations._transport import build

_built = build(_http)
VeuTransport = _built.VeuTransport
AsyncVeuTransport = _built.AsyncVeuTransport
client = _built.client
async_client = _built.async_client

__all__ = ["AsyncVeuTransport", "VeuTransport", "async_client", "client"]
