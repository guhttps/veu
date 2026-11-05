"""Transporte do Véu para o httpx2, usado pelos SDKs OpenAI 3.x e Anthropic 2.x.

    import httpx2
    from anthropic import Anthropic
    from veu.integrations.httpx2 import VeuTransport

    cliente = Anthropic(http_client=httpx2.Client(transport=VeuTransport()))
"""

import httpx2 as _http

from veu.integrations._transport import build

_built = build(_http)
VeuTransport = _built.VeuTransport
AsyncVeuTransport = _built.AsyncVeuTransport
client = _built.client
async_client = _built.async_client

__all__ = ["AsyncVeuTransport", "VeuTransport", "async_client", "client"]
