"""Fachada que monta detectores e anonimizador a partir da configuração."""

from __future__ import annotations

import os

from veu.analyzer import Analyzer
from veu.anonymizer import AnonymizationResult, Anonymizer
from veu.config import Config
from veu.entities import Entity
from veu.recognizers import (
    DEFAULT_SPECS,
    AddressRecognizer,
    LLMRecognizer,
    PatternRecognizer,
    PersonRecognizer,
    Recognizer,
    SpacyRecognizer,
    custom_spec,
)
from veu.vault import Vault


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
        elif name == "spacy":
            recognizers.append(SpacyRecognizer(config.spacy_model))
        elif name == "llm":
            if not config.llm_url or not config.llm_model:
                raise ValueError('O detector "llm" precisa de [deteccao.llm] url e modelo no veu.toml.')
            key = os.environ.get(config.llm_key_env) if config.llm_key_env else None
            recognizers.append(LLMRecognizer(config.llm_url, config.llm_model, key))
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
    """

    def __init__(self, config: Config | None = None, **options):
        config = config or Config()
        if options:
            config = config.with_overrides(**options)
        self.config = config
        self.analyzer = Analyzer(
            build_recognizers(config), threshold=config.threshold, labels=config.labels or None,
            allowlist=config.allowlist,
        )
        self.anonymizer = Anonymizer(
            self.analyzer, operator=config.operator, operators=config.operators, link_names=config.link_names,
            secret=config.secret.encode() if config.secret else None,
        )

    def analyze(self, text: str) -> list[Entity]:
        return self.analyzer.analyze(text)

    def anonymize(self, text: str, vault: Vault | None = None) -> AnonymizationResult:
        return self.anonymizer.anonymize(text, vault)

    def restore(self, text: str, vault: Vault) -> str:
        return vault.restore(text)

    def new_vault(self) -> Vault:
        return self.anonymizer.new_vault()
