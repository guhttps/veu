"""Fachada que monta detectores e anonimizador a partir da configuração."""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable
from importlib.metadata import entry_points

from veu.analyzer import Analyzer
from veu.anonymizer import AnonymizationResult, Anonymizer
from veu.config import PLUGIN_GROUP, Config, ConfigError
from veu.entities import Entity
from veu.recognizers import (
    DEFAULT_SPECS,
    AddressRecognizer,
    LLMRecognizer,
    PatternRecognizer,
    PersonRecognizer,
    Recognizer,
    SecretRecognizer,
    SpacyRecognizer,
    custom_spec,
)
from veu.vault import Vault


def load_plugin(name: str) -> Recognizer:
    """Carrega um detector de terceiros: "pacote.modulo:Classe" ou o nome de um entry point de veu.detectores.

    Um detector é qualquer objeto com name, labels e find(texto) -> candidatos (veja veu.recognizers.base).
    """
    if ":" in name:
        module_name, _, attribute = name.partition(":")
        try:
            target = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as exc:
            raise ConfigError(f'Não foi possível carregar o detector "{name}": {exc}') from exc
    else:
        found = list(entry_points(group=PLUGIN_GROUP, name=name))
        if not found:
            raise ConfigError(f'Detector "{name}" não encontrado nos plugins instalados.')
        target = found[0].load()
    recognizer = target() if isinstance(target, type) or not hasattr(target, "find") else target
    if not all(hasattr(recognizer, attribute) for attribute in ("name", "labels", "find")):
        raise ConfigError(f'O detector "{name}" precisa ter name, labels e find(texto).')
    return recognizer


def build_recognizers(config: Config) -> list[Recognizer]:
    custom = [
        custom_spec(
            pattern["entidade"], pattern["padrao"], float(pattern.get("pontuacao", 0.9)),
            pattern.get("contexto", ()), bool(pattern.get("exige_contexto", False)),
        )
        for pattern in config.custom_patterns
    ]
    recognizers: list[Recognizer] = []
    for name in config.detectors:
        if name == "padroes":
            recognizers.append(PatternRecognizer([*DEFAULT_SPECS, *custom]))
        elif name == "nomes":
            recognizers.append(PersonRecognizer())
        elif name == "enderecos":
            recognizers.append(AddressRecognizer())
        elif name == "segredos":
            recognizers.append(SecretRecognizer())
        elif name == "spacy":
            recognizers.append(SpacyRecognizer(config.spacy_model))
        elif name == "llm":
            if not config.llm_url or not config.llm_model:
                raise ValueError('O detector "llm" precisa de [deteccao.llm] url e modelo no veu.toml.')
            key = os.environ.get(config.llm_key_env) if config.llm_key_env else None
            recognizers.append(LLMRecognizer(config.llm_url, config.llm_model, key))
        else:
            recognizers.append(load_plugin(name))
    if custom and "padroes" not in config.detectors:
        recognizers.append(PatternRecognizer(custom))
    return recognizers


class Veu:
    """Ponto de entrada da biblioteca.

    >>> veu = Veu()
    >>> resultado = veu.anonymize("CPF 529.982.247-25")
    >>> resultado.text
    'CPF [CPF_1]'
    >>> veu.restore("Seu CPF é [CPF_1]", resultado.vault)
    'Seu CPF é 529.982.247-25'

    extra_recognizers: detectores próprios, somados aos da configuração.
    """

    def __init__(self, config: Config | None = None, *, extra_recognizers: Iterable[Recognizer] = (), **options):
        config = config or Config()
        if options:
            config = config.with_overrides(**options)
        self.config = config
        from veu.cache import DetectionCache

        self.analyzer = Analyzer(
            [*build_recognizers(config), *extra_recognizers], threshold=config.threshold,
            labels=config.labels or None, allowlist=config.allowlist, allow_patterns=config.allow_patterns,
            cache=DetectionCache(config.detection_cache) if config.detection_cache > 0 else None,
        )
        self.anonymizer = Anonymizer(
            self.analyzer, operator=config.operator, operators=config.operators, link_names=config.link_names,
            secret=config.secret.encode() if config.secret else None, policy=config.restore_policy(),
        )

    def analyze(self, text: str) -> list[Entity]:
        return self.analyzer.analyze(text)

    def anonymize(self, text: str, vault: Vault | None = None) -> AnonymizationResult:
        return self.anonymizer.anonymize(text, vault)

    def restore(self, text: str, vault: Vault) -> str:
        return vault.restore(text)

    def new_vault(self) -> Vault:
        return self.anonymizer.new_vault()

    def session(self, vault: Vault | None = None):
        """Sessão com um cofre compartilhado por várias chamadas (veja veu.sessions.Session)."""
        from veu.sessions import Session

        return Session(self.anonymizer, vault)

    def with_operator(self, operator: str) -> Veu:
        """Outra instância com o mesmo detector e outro operador (reaproveita os detectores carregados)."""
        clone = object.__new__(Veu)
        clone.config = self.config.with_overrides(operator=operator)
        clone.analyzer = self.analyzer
        clone.anonymizer = Anonymizer(
            self.analyzer, operator=operator, operators=self.config.operators, link_names=self.config.link_names,
            secret=self.config.secret.encode() if self.config.secret else None,
            policy=self.config.restore_policy(),
        )
        return clone
