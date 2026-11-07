"""Compara o vazamento do Véu e do Microsoft Presidio nos mesmos textos em português.

Rode num ambiente separado (o Presidio e o spaCy não são dependências do Véu):

    uv venv --python 3.12 .venv-presidio
    uv pip install --python .venv-presidio presidio-analyzer "spacy>=3.7,<3.9"
    .venv-presidio/Scripts/python -m spacy download pt_core_news_lg     # Linux/macOS: .venv-presidio/bin/python
    .venv-presidio/Scripts/python scripts/comparar_presidio.py --limite 3000

Configuração do Presidio, a mais justa que ele oferece em português sem código próprio: spaCy pt_core_news_lg
para nomes e locais e os reconhecedores prontos que não dependem de idioma (e-mail, telefone com a região BR,
cartão, IBAN, IP, URL, data), declarados para "pt". O Presidio não traz reconhecedores de documentos brasileiros
(CPF, CNPJ, RG...): é isso que se compara, o uso pronto de cada ferramenta.

O vazamento conta uma menção como protegida só se todos os seus caracteres alfanuméricos foram escondidos,
independentemente do tipo que a ferramenta deu. Assim os rótulos diferentes das duas ferramentas não pesam.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from veu.bench.desafio import challenge_samples  # noqa: E402
from veu.bench.evaluate import evaluate  # noqa: E402
from veu.bench.external import load_external  # noqa: E402
from veu.core import Veu  # noqa: E402


@dataclass
class Found:
    label: str
    start: int
    end: int
    text: str
    score: float = 1.0


class _Result:
    def __init__(self, entities):
        self.entities = entities


class PresidioAdapter:
    """Mesma interface que o evaluate() usa do Véu: anonymize(texto).entities."""

    LABELS = {"PERSON": "PESSOA", "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "TELEFONE", "CREDIT_CARD": "CARTAO_CREDITO",
              "IBAN_CODE": "IBAN", "IP_ADDRESS": "IP", "LOCATION": "ENDERECO", "DATE_TIME": "DATA_NASCIMENTO",
              "URL": "URL"}

    def __init__(self, model: str = "pt_core_news_lg"):
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_analyzer.predefined_recognizers import (
            CreditCardRecognizer,
            DateRecognizer,
            EmailRecognizer,
            IbanRecognizer,
            IpRecognizer,
            PhoneRecognizer,
            SpacyRecognizer,
            UrlRecognizer,
        )

        engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "pt", "model_name": model}],
            # Os rótulos do spaCy em português são PER, LOC, ORG e MISC.
            "ner_model_configuration": {"model_to_presidio_entity_mapping": {"PER": "PERSON", "LOC": "LOCATION"}},
        }).create_engine()
        registry = RecognizerRegistry(supported_languages=["pt"])
        for recognizer in (
            SpacyRecognizer(supported_language="pt", supported_entities=["PERSON", "LOCATION"]),
            EmailRecognizer(supported_language="pt"), PhoneRecognizer(supported_language="pt", supported_regions=["BR"]),
            CreditCardRecognizer(supported_language="pt"), IbanRecognizer(supported_language="pt"),
            IpRecognizer(supported_language="pt"), UrlRecognizer(supported_language="pt"),
            DateRecognizer(supported_language="pt"),
        ):
            registry.add_recognizer(recognizer)
        self.analyzer = AnalyzerEngine(nlp_engine=engine, registry=registry, supported_languages=["pt"])

    def anonymize(self, text: str) -> _Result:
        results = self.analyzer.analyze(text=text, language="pt", score_threshold=0.35)
        return _Result([Found(self.LABELS.get(r.entity_type, r.entity_type), r.start, r.end, text[r.start:r.end],
                              r.score) for r in sorted(results, key=lambda r: r.start)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--limite", type=int, default=3000, help="amostras do privacy-filter-br (padrão: 3000)")
    args = parser.parse_args()

    sets = {"desafio do Véu": (challenge_samples(), {})}
    for name in ("br-agentic", "privacy-filter-br"):
        samples, skipped, _ = load_external(name, args.limite if name == "privacy-filter-br" else None)
        sets[name] = (samples, dict(skipped))
    tools = {"Véu": Veu(), "Presidio": PresidioAdapter()}
    print("| Conjunto | Ferramenta | Menções | Vazamento | IC 95% | Caracteres/s |")
    print("|---|---|---:|---:|---:|---:|")
    for set_name, (samples, _) in sets.items():
        for tool_name, tool in tools.items():
            started = time.perf_counter()
            report = evaluate(samples, tool)
            seconds = time.perf_counter() - started
            low, high = report.leak_interval()
            speed = round(sum(len(s.text) for s in samples) / seconds)
            print(f"| {set_name} | {tool_name} | {report.overall.total} | {report.overall.leak_rate:.1%} | "
                  f"{low:.1%} a {high:.1%} | {speed:,} |".replace(",", "_").replace(".", ",").replace("_", "."),
                  flush=True)
    print("\nVazamento por tipo (privacy-filter-br):\n")
    samples, _ = sets["privacy-filter-br"]
    reports = {name: evaluate(samples, tool) for name, tool in tools.items()}
    print("| Tipo | Menções | " + " | ".join(f"Vazamento {name}" for name in tools) + " |")
    print("|---|---:|" + "---:|" * len(tools))
    labels = sorted(reports["Véu"].labels, key=lambda label: -reports["Véu"].labels[label].total)
    for label in labels:
        cells = [f"{reports[name].labels[label].leak_rate:.1%}" for name in tools]
        print(f"| {label} | {reports['Véu'].labels[label].total} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
