"""Filtro de logging que esconde dados pessoais das mensagens de log (e das exceções).

    import logging
    from veu.integrations.logging import protect_logs

    logging.basicConfig(level=logging.INFO)
    protect_logs()
    logging.info("Cliente CPF 529.982.247-25 logou")   # INFO:root:Cliente CPF [CPF] logou
"""

from __future__ import annotations

import logging

from veu.core import Veu


class PIIFilter(logging.Filter):
    """Troca dados pessoais das mensagens por [CPF], [PESSOA]... (operador "remover" por padrão)."""

    def __init__(self, veu: Veu | None = None, operator: str = "remover", name: str = ""):
        super().__init__(name)
        self.veu = veu or Veu(operator=operator)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = self.veu.anonymize(message).text
        if masked != message:
            record.msg = masked
            record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = self.veu.anonymize(logging.Formatter().formatException(record.exc_info)).text
        return True


def protect_logs(logger: logging.Logger | None = None, operator: str = "remover", veu: Veu | None = None) -> PIIFilter:
    """Adiciona o filtro a todos os handlers do logger (por padrão, o logger raiz)."""
    logger = logger or logging.getLogger()
    pii_filter = PIIFilter(veu, operator)
    if not logger.handlers:
        logging.basicConfig()
    for handler in logger.handlers:
        handler.addFilter(pii_filter)
    return pii_filter
