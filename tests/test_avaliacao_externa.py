"""Avaliação com conjuntos públicos de terceiros: carregadores, conferência do sha256 e intervalo de confiança."""

import hashlib
import io
import json

import pytest

from veu.bench import external
from veu.bench.evaluate import evaluate
from veu.bench.generator import Sample

CONVERSA = {
    "conversation_id": "c1",
    "messages": [
        {"role": "user", "content": "Sou Marina Albuquerque, CPF 529.982.247-25.", "pii_spans": [
            {"text": "Marina Albuquerque", "label": "PERSON_NAME", "start": 4, "end": 22, "field_type": "text_content"},
            {"text": "529.982.247-25", "label": "CPF", "start": 28, "end": 42, "field_type": "text_content"},
        ]},
        {"role": "assistant", "content": "Vou atualizar.", "pii_spans": [], "tool_calls": [{
            "id": "t1", "type": "function",
            "function": {"name": "atualizar", "arguments": '{"cpf": "529.982.247-25", "valor": "R$ 10,00"}'},
        }]},
        {"role": "assistant", "content": None, "pii_spans": [
            {"text": "529.982.247-25", "label": "CPF", "start": 9, "end": 23, "field_type": "tool_argument",
             "tool_call_id": "t1"},
            {"text": "R$ 10,00", "label": "FINANCIAL_VALUE", "start": 36, "end": 44, "field_type": "tool_argument",
             "tool_call_id": "t1"},
        ]},
    ],
}


def test_br_agentic_loader_evaluates_each_json_value_alone(tmp_path):
    path = tmp_path / "conversa.jsonl"
    # As anotações dos argumentos ficam na mesma mensagem que tem as chamadas.
    message = CONVERSA["messages"][1] | {"pii_spans": CONVERSA["messages"][2]["pii_spans"]}
    data = {**CONVERSA, "messages": [CONVERSA["messages"][0], message]}
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    samples, skipped = external._load_br_agentic(path, external.DATASETS["br-agentic"].labels)
    assert skipped == {"FINANCIAL_VALUE": 1}
    texts = {sample.text: sample.entities for sample in samples}
    assert texts["Sou Marina Albuquerque, CPF 529.982.247-25."] == [(4, 22, "PESSOA"), (28, 42, "CPF")]
    assert texts["529.982.247-25"] == [(0, 14, "CPF")]  # o valor sozinho, como o proxy esconde
    assert texts["R$ 10,00"] == []  # fora do escopo: não conta como vazamento
    assert "cpf" not in texts  # chaves do JSON não viram amostras


def test_privacy_filter_loader_maps_labels(tmp_path):
    path = tmp_path / "holdout.jsonl"
    text = "Nome: Marina Albuquerque | Pedido 123"
    path.write_text(json.dumps({"text": text, "template": "t", "entities": [
        {"start": 6, "end": 24, "label": "private_person"}, {"start": 34, "end": 37, "label": "private_order_id"},
    ]}) + "\n", encoding="utf-8")
    samples, skipped = external._load_privacy_filter_br(path, external.DATASETS["privacy-filter-br"].labels)
    assert samples[0].entities == [(6, 24, "PESSOA")] and skipped == {"private_order_id": 1}


def test_fetch_refuses_a_file_with_another_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("VEU_CACHE", str(tmp_path))
    dataset = external.DATASETS["br-agentic"]
    monkeypatch.setattr(external.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"outro arquivo"))
    with pytest.raises(ValueError, match="sha256"):
        external.fetch(dataset)
    assert not list(tmp_path.rglob("*.jsonl"))
    content = b'{"ok": true}\n'
    good = external.ExternalDataset(**{**dataset.__dict__, "sha256": hashlib.sha256(content).hexdigest()})
    monkeypatch.setattr(external.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(content))
    assert external.fetch(good).read_bytes() == content


def test_unknown_dataset():
    with pytest.raises(ValueError, match="Conjunto desconhecido"):
        external.load_external("nao-existe")


def test_leak_interval_and_out_of_scope_in_report():
    samples = [Sample("Marina Albuquerque ligou.", [(0, 18, "PESSOA")]), Sample("oi", []),
               Sample("CPF 529.982.247-25", [(4, 18, "CPF")])]
    report = evaluate(samples)
    assert report.leak_interval() == (0.0, 0.0)
    report.out_of_scope = {"FINANCIAL_VALUE": 3}
    text = report.to_markdown(precision=False)
    assert "IC 95% do vazamento" in text and "Precisão" not in text and "FINANCIAL_VALUE (3)" in text
    data = report.to_dict()
    assert data["geral"]["vazamento_ic95"] == [0.0, 0.0] and data["fora_do_escopo"] == {"FINANCIAL_VALUE": 3}
    leaky = evaluate([Sample("fala ae rayane, blz?", [(8, 14, "PESSOA")])] * 5 + samples)
    low, high = leaky.leak_interval("PESSOA")
    assert 0 <= low <= leaky.labels["PESSOA"].leak_rate <= high <= 1


def test_challenge_set_is_frozen():
    """O conjunto de desafio não pode ser editado: casos novos vão para um conjunto novo (desafio_v2)."""
    from veu.bench.desafio import CASES, challenge_samples, fingerprint

    assert fingerprint() == "e4384756062262ede1318dc9baf3a58dcfc067dfd163c03beebffe55738c6c4a"
    samples = challenge_samples()
    assert len(samples) == len(CASES) >= 40
    assert sum(len(sample.entities) for sample in samples) >= 50
    assert sum(not sample.entities for sample in samples) >= 8  # textos sem dados medem falsos positivos


def test_max_leak_gate_ignores_the_challenge_set(capsys):
    from veu.cli import main

    assert main(["avaliar", "--quantidade", "50", "--max-vazamento", "0.05"]) == 0
    assert "Conjunto: desafio" in capsys.readouterr().out
