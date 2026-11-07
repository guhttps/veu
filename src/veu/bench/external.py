"""Conjuntos públicos de terceiros, em português, para medir o Véu fora dos dados que ele mesmo gera.

    veu avaliar --externo br-agentic
    veu avaliar --externo privacy-filter-br --limite 2000

Os arquivos são baixados uma vez (versão fixa, conferida pelo sha256) para a pasta de cache do Véu. Os dois
conjuntos são sintéticos, mas foram escritos por outras pessoas, com outros textos e outras escolhas de anotação:
medem a generalização melhor do que o benchmark do próprio Véu.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from veu.bench.generator import Sample


@dataclass(frozen=True)
class ExternalDataset:
    name: str
    title: str
    url: str
    sha256: str
    license: str
    page: str
    labels: dict[str, str | None]  # rótulo do conjunto -> rótulo do Véu (None: fora do escopo do Véu)
    loader: Callable[[Path, dict[str, str | None]], tuple[list[Sample], Counter]]


def _string_literals(raw: str):
    """(início, fim, conteúdo) de cada string JSON que é um valor (não uma chave)."""
    for match in re.finditer(r'"((?:[^"\\]|\\.)*)"', raw):
        following = raw[match.end():].lstrip()[:1]
        if following != ":":
            yield match.start(1), match.end(1), match.group(1)


def _load_br_agentic(path: Path, labels: dict[str, str | None]) -> tuple[list[Sample], Counter]:
    """Conversas bancárias com chamadas de ferramenta: cada texto, argumento e resultado vira uma amostra.

    Nos argumentos de ferramentas, cada valor do JSON é avaliado sozinho, como o proxy do Véu faz.
    """
    samples: list[Sample] = []
    skipped: Counter = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        conversation = json.loads(line)
        for message in conversation["messages"]:
            spans = message.get("pii_spans") or []
            text_spans, argument_spans = [], {}
            for span in spans:
                label = labels.get(span["label"])
                if label is None:
                    skipped[span["label"]] += 1
                    continue
                if span.get("field_type") == "tool_argument":
                    argument_spans.setdefault(span.get("tool_call_id"), []).append((span["start"], span["end"], label))
                else:
                    text_spans.append((span["start"], span["end"], label))
            if message.get("content"):
                samples.append(Sample(message["content"], sorted(text_spans), f"br-agentic:{message['role']}"))
            for call in message.get("tool_calls") or []:
                raw = call.get("function", {}).get("arguments") or ""
                wanted = argument_spans.get(call.get("id"), [])
                for start, end, content in _string_literals(raw):
                    if "\\" in content:
                        continue  # com escapes, as posições do texto JSON não batem com as do valor
                    inner = [(s - start, e - start, label) for s, e, label in wanted if start <= s and e <= end]
                    samples.append(Sample(content, inner, "br-agentic:argumento"))
    return samples, skipped


def _load_privacy_filter_br(path: Path, labels: dict[str, str | None]) -> tuple[list[Sample], Counter]:
    samples: list[Sample] = []
    skipped: Counter = Counter()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            document = json.loads(line)
            spans = []
            for entity in document["entities"]:
                label = labels.get(entity["label"])
                if label is None:
                    skipped[entity["label"]] += 1
                else:
                    spans.append((entity["start"], entity["end"], label))
            samples.append(Sample(document["text"], sorted(spans), f"privacy-filter-br:{document.get('template', '')}"))
    return samples, skipped


DATASETS: dict[str, ExternalDataset] = {
    "br-agentic": ExternalDataset(
        name="br-agentic",
        title="BR-Agentic-PII-Benchmark (Guardion)",
        url="https://huggingface.co/datasets/guardion/BR-Agentic-PII-Benchmark/resolve/"
            "fc4efbeb23a08516cf9043ae6f7147e80055a83a/dataset.jsonl",
        sha256="b7700a0cd6ac679bc8bc5d31f36cf5c991ae3581d67caf6e38198557251bea6e",
        license="MIT",
        page="https://huggingface.co/datasets/guardion/BR-Agentic-PII-Benchmark",
        labels={
            "PERSON_NAME": "PESSOA", "CPF": "CPF", "EMAIL": "EMAIL", "PHONE_NUMBER": "TELEFONE",
            "STREET_ADDRESS": "ENDERECO", "BANK_ACCOUNT": "CONTA_BANCARIA", "BANK_BRANCH": "CONTA_BANCARIA",
            "PIX_KEY": "CHAVE_PIX", "CREDIT_CARD": "CARTAO_CREDITO",
            "FINANCIAL_VALUE": None,  # valores em reais não são dado pessoal sozinhos; o Véu não os esconde
        },
        loader=_load_br_agentic,
    ),
    "privacy-filter-br": ExternalDataset(
        name="privacy-filter-br",
        title="privacy-filter-br, conjunto holdout v8.1 (Lucian Fialho)",
        url="https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset/resolve/"
            "6c35d39ebf518fe59a273d410f372bdd63ac179e/holdout.jsonl",
        sha256="127ebb7c8ab69a650d12583de42ecb15c771e23453c55a5d9681eecd18f452db",
        license="Apache-2.0",
        page="https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset",
        labels={
            "private_person": "PESSOA", "private_phone": "TELEFONE", "private_email": "EMAIL", "private_cpf": "CPF",
            "private_address": "ENDERECO", "private_cnpj": "CNPJ", "private_rg": "RG", "private_pis": "PIS",
            "private_cnh": "CNH", "private_titulo_eleitor": "TITULO_ELEITOR", "account_number": "CONTA_BANCARIA",
            "secret": "SEGREDO",
            # Fora do escopo do Véu hoje: datas quaisquer, URLs, faturamento, inscrição estadual, números de
            # pedido, cliente, nota fiscal, transação, rastreio e certidão.
            "private_date": None, "private_url": None, "private_client_revenue": None, "private_ie": None,
            "private_order_id": None, "private_customer_id": None, "private_invoice_number": None,
            "private_transaction_id": None, "private_tracking_code": None, "private_certidao": None,
        },
        loader=_load_privacy_filter_br,
    ),
}
# Parte de treino do mesmo conjunto (230 MB): é nela que se investigam os erros, para o holdout continuar sendo teste.
DATASETS["privacy-filter-br-treino"] = ExternalDataset(
    name="privacy-filter-br-treino",
    title="privacy-filter-br, parte de treino v8.1 (Lucian Fialho), para investigar erros",
    url="https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset/resolve/"
        "6c35d39ebf518fe59a273d410f372bdd63ac179e/train.jsonl",
    sha256="bdeafc1734706dca4a34e9b9a18a3b0c05e91dcd7ae236bb7be5229663dafd96",
    license="Apache-2.0",
    page="https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset",
    labels=DATASETS["privacy-filter-br"].labels,
    loader=_load_privacy_filter_br,
)
# Conjuntos de teste: o ajuste dos detectores nunca olha para eles.
TEST_SETS = ("br-agentic", "privacy-filter-br")


def cache_dir() -> Path:
    if os.environ.get("VEU_CACHE"):
        return Path(os.environ["VEU_CACHE"]) / "datasets"
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "veu" / "cache" / "datasets"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "veu" / "datasets"


def fetch(dataset: ExternalDataset) -> Path:
    """Baixa o arquivo (uma vez) e confere o sha256: um arquivo diferente do esperado nunca é usado."""
    target = cache_dir() / f"{dataset.name}-{dataset.sha256[:12]}.jsonl"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"Baixando {dataset.title} ({dataset.license})...", file=sys.stderr)
        request = urllib.request.Request(dataset.url, headers={"User-Agent": "veu-avaliar"})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (URL fixa, https)
            content = response.read()
        if hashlib.sha256(content).hexdigest() != dataset.sha256:
            raise ValueError(f"O arquivo baixado de {dataset.url} não confere com o sha256 esperado.")
        partial = target.with_suffix(".parcial")
        partial.write_bytes(content)
        partial.replace(target)
    return target


def load_external(name: str, limit: int | None = None) -> tuple[list[Sample], Counter, ExternalDataset]:
    """Amostras do conjunto, tipos fora do escopo do Véu (com contagem) e a descrição do conjunto."""
    if name not in DATASETS:
        raise ValueError(f"Conjunto desconhecido: {name}. Use um de {', '.join(DATASETS)}.")
    dataset = DATASETS[name]
    samples, skipped = dataset.loader(fetch(dataset), dataset.labels)
    if limit:
        samples = samples[:limit]
    return samples, skipped, dataset
