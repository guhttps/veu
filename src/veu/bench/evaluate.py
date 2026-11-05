"""Avaliação do Véu: precisão, revocação e taxa de vazamento por tipo de dado."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from veu.bench.generator import Sample
from veu.core import Veu


@dataclass
class LabelReport:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    protected: int = 0
    total: int = 0

    @property
    def precision(self) -> float:
        found = self.true_positives + self.false_positives
        return self.true_positives / found if found else 1.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + self.false_negatives
        return self.true_positives / expected if expected else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def leak_rate(self) -> float:
        return 1 - self.protected / self.total if self.total else 0.0


@dataclass
class Report:
    labels: dict[str, LabelReport] = field(default_factory=lambda: defaultdict(LabelReport))
    samples: int = 0
    characters: int = 0
    seconds: float = 0.0
    leaks: list[tuple[str, str, str]] = field(default_factory=list)
    false_positives: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def overall(self) -> LabelReport:
        total = LabelReport()
        for report in self.labels.values():
            total.true_positives += report.true_positives
            total.false_positives += report.false_positives
            total.false_negatives += report.false_negatives
            total.protected += report.protected
            total.total += report.total
        return total

    def to_dict(self) -> dict:
        def row(report: LabelReport) -> dict:
            return {
                "ocorrencias": report.total,
                "precisao": round(report.precision, 4),
                "revocacao": round(report.recall, 4),
                "f1": round(report.f1, 4),
                "vazamento": round(report.leak_rate, 4),
                "falsos_positivos": report.false_positives,
            }

        return {
            "amostras": self.samples,
            "caracteres_por_segundo": round(self.characters / self.seconds) if self.seconds else None,
            "geral": row(self.overall),
            "por_entidade": {label: row(report) for label, report in sorted(self.labels.items())},
        }

    def to_markdown(self) -> str:
        lines = [
            "| Entidade | Ocorrências | Precisão | Revocação | F1 | Vazamento |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for label, report in sorted(self.labels.items(), key=lambda item: -item[1].total):
            if not report.total and not report.false_positives:
                continue
            lines.append(
                f"| {label} | {report.total} | {report.precision:.1%} | {report.recall:.1%} | {report.f1:.1%} | "
                f"{report.leak_rate:.1%} |"
            )
        overall = self.overall
        lines.append(
            f"| **Geral** | **{overall.total}** | **{overall.precision:.1%}** | **{overall.recall:.1%}** | "
            f"**{overall.f1:.1%}** | **{overall.leak_rate:.1%}** |"
        )
        return "\n".join(lines).replace(".", ",").replace("|---,", "|---.")


def _covered(start: int, end: int, text: str, spans: list[tuple[int, int]]) -> bool:
    """Todos os caracteres alfanuméricos do trecho ficaram escondidos?"""
    return all(
        not text[index].isalnum() or any(s <= index < e for s, e in spans) for index in range(start, end)
    )


def evaluate(samples: list[Sample], veu: Veu | None = None) -> Report:
    veu = veu or Veu()
    report = Report()
    started = time.perf_counter()
    for sample in samples:
        predictions = veu.anonymize(sample.text).entities
        report.samples += 1
        report.characters += len(sample.text)
        spans = [(entity.start, entity.end) for entity in predictions]
        matched_predictions: set[int] = set()
        for start, end, label in sample.entities:
            stats = report.labels[label]
            stats.total += 1
            hit = next(
                (i for i, e in enumerate(predictions) if e.label == label and e.start < end and start < e.end), None
            )
            if hit is None:
                stats.false_negatives += 1
            else:
                stats.true_positives += 1
                matched_predictions.add(hit)
            if _covered(start, end, sample.text, spans):
                stats.protected += 1
            else:
                report.leaks.append((label, sample.text[start:end], sample.text))
        for index, entity in enumerate(predictions):
            if index in matched_predictions:
                continue
            same = any(entity.label == label and entity.start < end and start < entity.end
                       for start, end, label in sample.entities)
            if not same:
                report.labels[entity.label].false_positives += 1
                report.false_positives.append((entity.label, entity.text, sample.text))
    report.seconds = time.perf_counter() - started
    return report
