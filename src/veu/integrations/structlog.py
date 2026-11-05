"""Processador do structlog que esconde dados pessoais dos eventos de log.

    import structlog
    from veu.integrations.structlog import PIIProcessor

    structlog.configure(processors=[PIIProcessor(), structlog.processors.JSONRenderer()])

Coloque-o antes do renderizador. Não depende do pacote structlog.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from veu.core import Veu


class PIIProcessor:
    """Troca dados pessoais dos valores do evento por [CPF], [PESSOA]... (operador "remover" por padrão).

    keys: analisa só estas chaves (padrão: todas, menos timestamp, level e logger).
    """

    _SKIP = frozenset({"timestamp", "level", "logger", "logger_name", "lineno", "func_name", "filename"})

    def __init__(self, veu: Veu | None = None, operator: str = "remover", keys: Iterable[str] | None = None):
        self._veu = veu
        self._operator = operator
        self.keys = set(keys) if keys is not None else None

    @property
    def veu(self) -> Veu:
        if self._veu is None:
            self._veu = Veu(operator=self._operator)
        return self._veu

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.veu.anonymize(value).text
        if isinstance(value, dict):
            return {key: self._scrub(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self._scrub(item) for item in value)
        return value

    def __call__(self, logger, method_name: str, event_dict: dict) -> dict:
        for key, value in list(event_dict.items()):
            if key in self._SKIP or (self.keys is not None and key not in self.keys):
                continue
            event_dict[key] = self._scrub(value)
        return event_dict
