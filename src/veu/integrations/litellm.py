"""Guardrail do Véu para o LiteLLM Proxy (pip install "veu[litellm]").

Para empresas que já centralizam o acesso às IAs no LiteLLM: o Véu entra como guardrail, sem proxy novo e sem
instalar nada nos computadores. No config.yaml do LiteLLM:

    guardrails:
      - guardrail_name: veu
        litellm_params:
          guardrail: veu.integrations.litellm.VeuGuardrail
          mode: [pre_call, post_call]
          default_on: true
          veu_config: /etc/veu/veu.toml      # opcional (padrão: VEU_CONFIG ou ./veu.toml)

A configuração do Véu (tipos, operadores, bloqueios) vem desse veu.toml.
O cofre fica só na memória do guardrail: os metadados da requisição (que o LiteLLM pode registrar em logs)
recebem apenas um identificador.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections import OrderedDict
from typing import Any

from litellm.integrations.custom_guardrail import CustomGuardrail

from veu.config import load_config
from veu.core import Veu
from veu.gateway.adapters import (
    AnthropicMessagesAdapter,
    Masker,
    OpenAIChatAdapter,
    OpenAICompletionsAdapter,
    OpenAIEmbeddingsAdapter,
    OpenAIResponsesAdapter,
    restore_json_string,
)
from veu.gateway.pipeline import INSTRUCTION
from veu.vault import StreamRestorer, Vault

_ADAPTERS = {
    "completion": OpenAIChatAdapter(), "acompletion": OpenAIChatAdapter(),
    "text_completion": OpenAICompletionsAdapter(), "atext_completion": OpenAICompletionsAdapter(),
    "embedding": OpenAIEmbeddingsAdapter(), "aembedding": OpenAIEmbeddingsAdapter(),
    "anthropic_messages": AnthropicMessagesAdapter(), "aanthropic_messages": AnthropicMessagesAdapter(),
    "responses": OpenAIResponsesAdapter(), "aresponses": OpenAIResponsesAdapter(),
}
_UNTOUCHED_KEYS = frozenset({"signature", "encrypted_content", "thinking_blocks", "reasoning_content"})
_UNTOUCHED_TYPES = frozenset({"thinking", "redacted_thinking", "reasoning"})
_KEY = "veu_id"


class BlockedError(ValueError):
    """Dados que a política manda bloquear (o LiteLLM devolve o erro ao cliente)."""


def _blocked(labels: list[str]) -> Exception:
    message = f"Requisição bloqueada pelo Véu: contém dados que a política não permite enviar ({', '.join(labels)})."
    try:
        from fastapi import HTTPException

        return HTTPException(status_code=400, detail={"error": message, "veu_bloqueado": labels})
    except ImportError:  # fora do proxy (testes, uso como biblioteca)
        return BlockedError(message)


def restore_in_place(value: Any, vault: Vault) -> Any:
    """Restaura todos os textos de uma resposta (dicts, listas e objetos pydantic do LiteLLM)."""
    if isinstance(value, str):
        return vault.restore(value)
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = restore_in_place(item, vault)
        return value
    if isinstance(value, dict):
        if value.get("type") in _UNTOUCHED_TYPES:
            return value
        for key, item in list(value.items()):
            if key in _UNTOUCHED_KEYS:
                continue
            if key in ("arguments", "partial_json") and isinstance(item, str):
                value[key] = restore_json_string(item, vault)
            else:
                value[key] = restore_in_place(item, vault)
        return value
    fields = getattr(type(value), "model_fields", None)
    if fields is not None:
        if getattr(value, "type", None) in _UNTOUCHED_TYPES:
            return value
        names = list(fields) + list((getattr(value, "model_extra", None) or {}).keys())
        for name in names:
            if name in _UNTOUCHED_KEYS:
                continue
            item = getattr(value, name, None)
            if item is None:
                continue
            if name in ("arguments", "partial_json") and isinstance(item, str):
                new = restore_json_string(item, vault)
            else:
                new = restore_in_place(item, vault)
            if new is not item:
                with contextlib.suppress(AttributeError, TypeError, ValueError):
                    setattr(value, name, new)
    return value


class VeuGuardrail(CustomGuardrail):
    """Esconde os dados antes da chamada (pre_call) e restaura a resposta (post_call), inclusive em streaming."""

    def __init__(self, veu: Veu | None = None, veu_config: str | None = None, max_pending: int = 10_000,
                 ttl: float = 3600.0, **kwargs):
        self.veu = veu or Veu(load_config(veu_config))
        self.max_pending = max_pending
        self.ttl = ttl
        self._vaults: OrderedDict[str, tuple[float, Vault]] = OrderedDict()
        super().__init__(**kwargs)

    # Cofres em memória, por requisição ----------------------------------------------------------------------------
    def _remember(self, data: dict, vault: Vault) -> None:
        metadata = data.setdefault("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
        key = metadata.get(_KEY) or uuid.uuid4().hex
        metadata[_KEY] = key
        now = time.monotonic()
        self._vaults[key] = (now, vault)
        while self._vaults and (len(self._vaults) > self.max_pending or now - next(iter(self._vaults.values()))[0] > self.ttl):
            self._vaults.popitem(last=False)

    def _vault_for(self, data: dict | None) -> Vault | None:
        key = ((data or {}).get("metadata") or {}).get(_KEY)
        entry = self._vaults.pop(key, None) if key else None
        return entry[1] if entry else None

    # Ganchos do LiteLLM -------------------------------------------------------------------------------------------
    async def async_pre_call_hook(self, user_api_key_dict: Any, cache: Any, data: dict, call_type: str):
        adapter = _ADAPTERS.get(call_type)
        if adapter is None:
            return data
        vault = self.veu.new_vault()
        masker = Masker(self.veu.anonymizer, vault)
        adapter.mask(data, masker)
        blocked = sorted(label for label in masker.counts if label in set(self.veu.config.block))
        if blocked:
            raise _blocked(blocked)
        if masker.counts:
            if self.veu.config.instruct_model and vault.has_placeholders:
                adapter.instruct(data, INSTRUCTION)
            if adapter.restores_output:
                self._remember(data, vault)
        return data

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict: Any, response: Any):
        vault = self._vault_for(data)
        if vault is not None and len(vault):
            restore_in_place(response, vault)
        return response

    async def async_post_call_streaming_iterator_hook(self, user_api_key_dict: Any, response: Any, request_data: dict):
        vault = self._vault_for(request_data)
        if vault is None or not len(vault):
            async for chunk in response:
                yield chunk
            return
        restorers: dict[tuple, StreamRestorer] = {}

        def feed(key: tuple, text: str, json_escape: bool = False) -> str:
            if key not in restorers:
                restorers[key] = vault.restorer(json_escape=json_escape)
            return restorers[key].feed(text)

        def flush(index: int) -> str:
            tail = ""
            for key in [k for k in restorers if k[0] == index and k[1] == "texto"]:
                tail += restorers.pop(key).flush()
            return tail

        last = None
        async for chunk in response:
            last = chunk
            for choice in getattr(chunk, "choices", None) or []:
                index = getattr(choice, "index", 0) or 0
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                if isinstance(getattr(delta, "content", None), str):
                    delta.content = feed((index, "texto"), delta.content)
                for call in getattr(delta, "tool_calls", None) or []:
                    function = getattr(call, "function", None)
                    if function is not None and isinstance(getattr(function, "arguments", None), str):
                        position = getattr(call, "index", 0) or 0
                        function.arguments = feed((index, "ferramenta", position), function.arguments, True)
                if getattr(choice, "finish_reason", None):
                    tail = flush(index)
                    if tail:
                        delta.content = (delta.content or "") + tail
            yield chunk
        pending = {key: restorer.flush() for key, restorer in restorers.items() if restorer.pending}
        text_tail = "".join(value for key, value in pending.items() if key[1] == "texto")
        if text_tail and last is not None:
            from litellm.types.utils import Delta, ModelResponseStream, StreamingChoices

            yield ModelResponseStream(id=getattr(last, "id", None), model=getattr(last, "model", None),
                                      choices=[StreamingChoices(index=0, delta=Delta(content=text_tail))])
