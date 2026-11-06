"""Logs e relatórios de erro sem dados pessoais: Sentry, structlog e loguru.

    pip install veu sentry-sdk structlog loguru
    python examples/observabilidade.py
"""

import sys

import structlog
from loguru import logger

from veu.integrations.loguru import pii_patcher
from veu.integrations.sentry import before_send
from veu.integrations.structlog import PIIProcessor

# Sentry: em produção, passe before_send e before_breadcrumb para sentry_sdk.init(...).
evento = {"message": "Falha no pagamento de Maria Souza (CPF 529.982.247-25)"}
print("sentry:", before_send(evento, {})["message"])

# structlog
structlog.configure(processors=[PIIProcessor(), structlog.processors.KeyValueRenderer()])
structlog.get_logger().info("cadastro", cliente="Maria Souza", email="maria@example.com")

# loguru
logger.remove()
logger.add(sys.stdout, format="loguru: {message} {extra}")
logger.configure(patcher=pii_patcher())
logger.bind(telefone="(11) 91234-5678").info("Novo pedido do CPF {}", "529.982.247-25")
