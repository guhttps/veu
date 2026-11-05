"""Detectores de dados pessoais."""

from veu.recognizers.addresses import AddressRecognizer
from veu.recognizers.base import Candidate, Recognizer
from veu.recognizers.optional import LLMRecognizer, SpacyRecognizer
from veu.recognizers.patterns import DEFAULT_SPECS, PatternRecognizer, PatternSpec, Scores, custom_spec
from veu.recognizers.persons import PersonRecognizer

__all__ = [
    "DEFAULT_SPECS",
    "AddressRecognizer",
    "Candidate",
    "LLMRecognizer",
    "PatternRecognizer",
    "PatternSpec",
    "PersonRecognizer",
    "Recognizer",
    "Scores",
    "SpacyRecognizer",
    "custom_spec",
]
