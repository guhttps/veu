"""Avaliação do Véu: precisão, revocação e taxa de vazamento por tipo de dado."""

from __future__ import annotations

import random
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
    # Por amostra: {rótulo: (ocorrências, protegidas)}, para o intervalo de confiança.
    per_sample: list[dict[str, tuple[int, int]]] = field(default_factory=list)
    # Tipos anotados no conjunto que o Véu não cobre (só em conjuntos externos).
    out_of_scope: dict[str, int] = field(default_factory=dict)

    def leak_interval(self, label: str | None = None, rounds: int = 1000, seed: int = 7) -> tuple[float, float]:
        """Intervalo de confiança de 95% do vazamento (bootstrap por amostra, com semente fixa)."""
        rows = [(sum(v[0] for v in item.values()), sum(v[1] for v in item.values())) if label is None
                else item.get(label, (0, 0)) for item in self.per_sample]
        rows = [row for row in rows if row[0]]
        if not rows:
            return 0.0, 0.0
        rng = random.Random(seed)
        size = len(rows)
        rates = []
        for _ in range(rounds):
            total = protected = 0
            for _ in range(size):
                count, safe = rows[rng.randrange(size)]
                total += count
                protected += safe
            rates.append(1 - protected / total)
        rates.sort()
        return rates[int(rounds * 0.025)], rates[min(rounds - 1, int(rounds * 0.975))]

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
        def row(report: LabelReport, label: str | None) -> dict:
            low, high = self.leak_interval(label)
            return {
                "ocorrencias": report.total,
                "precisao": round(report.precision, 4),
                "revocacao": round(report.recall, 4),
                "f1": round(report.f1, 4),
                "vazamento": round(report.leak_rate, 4),
                "vazamento_ic95": [round(low, 4), round(high, 4)],
                "falsos_positivos": report.false_positives,
            }

        data = {
            "amostras": self.samples,
            "caracteres_por_segundo": round(self.characters / self.seconds) if self.seconds else None,
            "geral": row(self.overall, None),
            "por_entidade": {label: row(report, label) for label, report in sorted(self.labels.items())},
        }
        if self.out_of_scope:
            data["fora_do_escopo"] = dict(sorted(self.out_of_scope.items()))
        return data

    def to_markdown(self, *, precision: bool = True) -> str:
        """precision=False para conjuntos externos: as anotações deles não cobrem tudo o que o Véu esconde
        (CEP dentro de endereços, datas), então a precisão por rótulo não seria justa."""

        def line(name: str, report: LabelReport, label: str | None, bold: bool = False) -> str:
            mark = "**" if bold else ""
            low, high = self.leak_interval(label)
            cells = [name, str(report.total)]
            if precision:
                cells.append(f"{report.precision:.1%}")
            cells.append(f"{report.recall:.1%}")
            if precision:
                cells.append(f"{report.f1:.1%}")
            cells += [f"{report.leak_rate:.1%}", f"{low:.1%} a {high:.1%}"]
            return "| " + " | ".join(f"{mark}{cell}{mark}" for cell in cells) + " |"

        if precision:
            lines = ["| Entidade | Ocorrências | Precisão | Revocação | F1 | Vazamento | IC 95% do vazamento |",
                     "|---|---:|---:|---:|---:|---:|---:|"]
        else:
            lines = ["| Entidade | Ocorrências | Revocação | Vazamento | IC 95% do vazamento |",
                     "|---|---:|---:|---:|---:|"]
        for label, report in sorted(self.labels.items(), key=lambda item: -item[1].total):
            if not report.total and (not report.false_positives or not precision):
                continue
            lines.append(line(label, report, label))
        lines.append(line("Geral", self.overall, None, bold=True))
        text = "\n".join(lines).replace(".", ",").replace("|---,", "|---.")
        if self.out_of_scope:
            items = ", ".join(f"{label} ({count})"
                              for label, count in sorted(self.out_of_scope.items(), key=lambda item: -item[1]))
            text += f"\n\nAnotados no conjunto, mas fora do que o Véu esconde: {items}."
        return text


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
        counts: dict[str, list[int]] = {}
        report.characters += len(sample.text)
        spans = [(entity.start, entity.end) for entity in predictions]
        matched_predictions: set[int] = set()
        for start, end, label in sample.entities:
            stats = report.labels[label]
            stats.total += 1
            counts.setdefault(label, [0, 0])[0] += 1
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
                counts[label][1] += 1
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
        report.per_sample.append({label: (total, safe) for label, (total, safe) in counts.items()})
    report.seconds = time.perf_counter() - started
    return report
