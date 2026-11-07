"""Véu: esconde dados pessoais e segredos antes de enviar textos para modelos de IA.

Uso rápido:

    import veu

    resultado = veu.anonymize("Sou a Maria Souza, CPF 529.982.247-25")
    resultado.text            # "Sou a [PESSOA_1], CPF [CPF_1]"
    veu.restore("Olá, [PESSOA_1]!", resultado.vault)   # "Olá, Maria Souza!"
"""

from __future__ import annotations

from veu.analyzer import Analyzer
from veu.anonymizer import OPERATORS, AnonymizationResult, Anonymizer
from veu.config import Config, ConfigError, load_config
from veu.core import Veu
from veu.entities import LABELS, Entity
from veu.vault import StreamRestorer, Vault

__version__ = "0.5.2"

__all__ = [
    "LABELS",
    "OPERATORS",
    "AnonymizationResult",
    "Analyzer",
    "Anonymizer",
    "Config",
    "ConfigError",
    "Entity",
    "StreamRestorer",
    "Vault",
    "Veu",
    "__version__",
    "analyze",
    "anonymize",
    "load_config",
    "protect",
    "restore",
    "session",
]

_default: Veu | None = None


def _instance() -> Veu:
    global _default
    if _default is None:
        _default = Veu()
    return _default


def analyze(text: str) -> list[Entity]:
    """Lista os dados pessoais encontrados no texto."""
    return _instance().analyze(text)


def anonymize(text: str, vault: Vault | None = None) -> AnonymizationResult:
    """Troca os dados pessoais por marcadores. O cofre do resultado restaura a resposta do modelo."""
    return _instance().anonymize(text, vault)


def restore(text: str, vault: Vault) -> str:
    """Devolve os dados reais no lugar dos marcadores."""
    return vault.restore(text)


def session(vault: Vault | None = None):
    """Sessão com um cofre compartilhado: anonymize, anonymize_data, restore, restore_stream."""
    return _instance().session(vault)


def protect(func=None, **options):
    """Decorador: anonimiza os argumentos e restaura o retorno (veja veu.integrations.decorator)."""
    from veu.integrations.decorator import protect as decorator

    return decorator(func, **options)
