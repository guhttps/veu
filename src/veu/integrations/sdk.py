"""Atalhos que criam clientes dos SDKs oficiais já protegidos pelo Véu.

    from veu.integrations.sdk import openai_client, anthropic_client

    openai = openai_client()          # mesmos argumentos de openai.OpenAI(...)
    claude = anthropic_client()       # mesmos argumentos de anthropic.Anthropic(...)

Cada atalho descobre se o SDK instalado usa o httpx ou o httpx2 e monta o transporte certo.
"""

from __future__ import annotations

import importlib

from veu.core import Veu


def _http_module(sdk: str) -> str:
    base = importlib.import_module(f"{sdk}._base_client")
    return "httpx2" if hasattr(base, "httpx2") else "httpx"


def _http_client(sdk: str, veu: Veu | None, asynchronous: bool):
    integration = importlib.import_module(f"veu.integrations.{_http_module(sdk)}")
    return integration.async_client(veu) if asynchronous else integration.client(veu)


def openai_client(veu: Veu | None = None, **kwargs):
    from openai import OpenAI

    return OpenAI(http_client=_http_client("openai", veu, False), **kwargs)


def async_openai_client(veu: Veu | None = None, **kwargs):
    from openai import AsyncOpenAI

    return AsyncOpenAI(http_client=_http_client("openai", veu, True), **kwargs)


def anthropic_client(veu: Veu | None = None, **kwargs):
    from anthropic import Anthropic

    return Anthropic(http_client=_http_client("anthropic", veu, False), **kwargs)


def async_anthropic_client(veu: Veu | None = None, **kwargs):
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(http_client=_http_client("anthropic", veu, True), **kwargs)
