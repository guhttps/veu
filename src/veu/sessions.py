"""Sessão: um cofre compartilhado por várias chamadas.

    import veu

    with veu.session() as sessao:
        pergunta = sessao.anonymize("Sou a Maria Souza, CPF 529.982.247-25")
        mensagens = sessao.anonymize_data([{"role": "user", "content": "..."}])
        resposta = chamar_modelo(pergunta)
        print(sessao.restore(resposta))
        for pedaco in sessao.restore_stream(stream_do_modelo):
            print(pedaco, end="")
"""

from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from typing import Any

from veu.anonymizer import Anonymizer
from veu.gateway.adapters import Masker, restore_obj
from veu.vault import StreamRestorer, Vault


class Session:
    def __init__(self, anonymizer: Anonymizer, vault: Vault | None = None):
        self.anonymizer = anonymizer
        self.vault = vault if vault is not None else anonymizer.new_vault()
        self._masker = Masker(anonymizer, self.vault)

    @property
    def counts(self) -> Counter[str]:
        """Quantos dados de cada tipo foram escondidos nesta sessão."""
        return self._masker.counts

    def anonymize(self, text: str) -> str:
        return self._masker.text(text)

    def anonymize_data(self, data: Any) -> Any:
        """Esconde os dados de todos os textos de dicts, listas e tuplas (as chaves não são alteradas)."""
        return self._masker.obj(data)

    def restore(self, text: str) -> str:
        return self.vault.restore(text)

    def restore_data(self, data: Any) -> Any:
        return restore_obj(data, self.vault)

    def restorer(self) -> StreamRestorer:
        return self.vault.restorer()

    def restore_stream(self, chunks: Iterable[str]) -> Iterator[str]:
        """Restaura uma resposta em streaming, remontando marcadores partidos entre pedaços."""
        restorer = self.vault.restorer()
        for chunk in chunks:
            output = restorer.feed(chunk)
            if output:
                yield output
        tail = restorer.flush()
        if tail:
            yield tail

    async def arestore_stream(self, chunks: AsyncIterable[str]) -> AsyncIterator[str]:
        restorer = self.vault.restorer()
        async for chunk in chunks:
            output = restorer.feed(chunk)
            if output:
                yield output
        tail = restorer.flush()
        if tail:
            yield tail

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc) -> None:
        return None
