"""Fluxo comum ao proxy e à integração com httpx: esconder, encaminhar e restaurar."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from veu.core import Veu
from veu.gateway.adapters import Adapter, Masker, StreamState, restore_obj
from veu.gateway.sse import NDJSONTransformer, SSETransformer
from veu.vault import Vault

INSTRUCTION = (
    "Alguns dados pessoais deste conteúdo foram trocados por marcadores entre colchetes, como [PESSOA_1] ou "
    "[CPF_1]. Quando precisar se referir a esses dados, repita o marcador exatamente como está, inclusive os "
    "colchetes. Não tente adivinhar nem completar os valores reais."
)


class BlockedError(Exception):
    """A requisição tem um tipo de dado que a política manda bloquear em vez de esconder."""

    def __init__(self, labels: list[str], counts: Counter[str]):
        self.labels = labels
        self.counts = counts
        names = ", ".join(labels)
        super().__init__(
            f"Requisição bloqueada pelo Véu: contém dados que a política não permite enviar ({names})."
        )


@dataclass
class Prepared:
    adapter: Adapter
    body: bytes
    vault: Vault
    counts: Counter[str]
    stream: bool


class Gateway:
    def __init__(self, veu: Veu | None = None):
        self.veu = veu or Veu()
        self.expander = None
        if self.veu.config.expand_links:
            from veu.sources import LinkExpander

            self.expander = LinkExpander(self.veu.config.expand_domains)

    @property
    def config(self):
        return self.veu.config

    def prepare(self, adapter: Adapter, body: bytes, vault: Vault | None = None, path: str = "",
                block: Iterable[str] | None = None) -> Prepared:
        """Esconde os dados pessoais do corpo da requisição. Levanta BlockedError ou ValueError (JSON inválido).

        block: tipos que fazem a requisição ser recusada (padrão: a política global).
        """
        payload = json.loads(body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("O corpo da requisição precisa ser um objeto JSON.")
        vault = self.veu.new_vault() if vault is None else vault
        masker = Masker(self.veu.anonymizer, vault, self.expander.expand if self.expander else None)
        adapter.mask(payload, masker)
        policy = set(self.config.block if block is None else block)
        blocked = sorted(label for label in masker.counts if label in policy)
        if blocked:
            raise BlockedError(blocked, masker.counts)
        if self.config.instruct_model and masker.counts and vault.has_placeholders:
            adapter.instruct(payload, INSTRUCTION)
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        return Prepared(adapter, encoded, vault, masker.counts, adapter.is_stream(payload, path))

    def restore_body(self, prepared: Prepared, body: bytes) -> bytes:
        """Restaura uma resposta JSON completa (sem streaming)."""
        if not prepared.adapter.restores_output or not len(prepared.vault) or not body:
            return body
        try:
            data = json.loads(body)
        except ValueError:
            return prepared.vault.restore(body.decode("utf-8", errors="replace")).encode()
        return json.dumps(restore_obj(data, prepared.vault), ensure_ascii=False).encode()

    def stream(self, prepared: Prepared, content_type: str = "text/event-stream") -> SSETransformer | NDJSONTransformer:
        """Transformador incremental para a resposta em streaming (SSE ou JSON por linha)."""
        state = StreamState(prepared.vault)
        adapter = prepared.adapter
        transformer = NDJSONTransformer if "ndjson" in content_type else SSETransformer
        return transformer(
            lambda name, data: adapter.stream_event(name, data, state),
            lambda: adapter.stream_finish(state),
        )


def is_streaming(content_type: str) -> bool:
    return "text/event-stream" in content_type or "ndjson" in content_type
