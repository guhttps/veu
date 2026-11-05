"""Patcher do loguru que esconde dados pessoais das mensagens e dos campos extras.

    from loguru import logger
    from veu.integrations.loguru import pii_patcher

    logger.configure(patcher=pii_patcher())

Não depende do pacote loguru.
"""

from __future__ import annotations

from collections.abc import Callable

from veu.core import Veu


def pii_patcher(veu: Veu | None = None, operator: str = "remover") -> Callable[[dict], None]:
    """Função para logger.configure(patcher=...) ou logger.patch(...)."""
    instance = veu or Veu(operator=operator)

    def patch(record: dict) -> None:
        record["message"] = instance.anonymize(record["message"]).text
        extra = record.get("extra")
        if isinstance(extra, dict):
            for key, value in list(extra.items()):
                if isinstance(value, str):
                    extra[key] = instance.anonymize(value).text

    return patch
