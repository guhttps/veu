"""Esconde dados pessoais dos logs da aplicação.

    pip install veu
    python examples/logs.py
"""

import logging

from veu.integrations.logging import protect_logs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
protect_logs()

logging.info("Novo cadastro: %s, CPF %s, e-mail %s", "Maria Souza", "529.982.247-25", "maria@example.com")
try:
    raise ValueError("Cartão 4111 1111 1111 1111 recusado")
except ValueError:
    logging.exception("Falha no pagamento")
# INFO Novo cadastro: [PESSOA], CPF [CPF], e-mail [EMAIL]
# ERROR Falha no pagamento
# Traceback (most recent call last): ... ValueError: Cartão [CARTAO_CREDITO] recusado
