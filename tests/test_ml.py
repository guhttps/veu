"""Detector "ml" (modelo BERT): só nomes, e só com confiança alta ou corroborados pelas listas ou pelo contexto."""

import pytest

from veu import Veu
from veu.config import ConfigError, load_config
from veu.recognizers.optional import MLRecognizer


def fake_pipeline(results):
    return lambda text: results(text) if callable(results) else results


def find(results, text):
    return [(c.label, text[c.start:c.end], c.score) for c in MLRecognizer(pipeline=fake_pipeline(results)).find(text)]


def test_names_are_corroborated_or_highly_confident():
    text = "Atendimento de Kawanny Prates e Bolota Zyx com Maria Tal."
    results = [
        {"entity_group": "NOME", "score": 0.7, "start": 15, "end": 29},   # "Kawanny Prates": Prates? kawanny? IBGE
        {"entity_group": "NOME", "score": 0.6, "start": 32, "end": 42},   # "Bolota Zyx": nem lista nem contexto
        {"entity_group": "NOME", "score": 0.95, "start": 47, "end": 56},  # confiança alta
        {"entity_group": "CPF", "score": 0.99, "start": 0, "end": 5},     # documentos ficam com as regras
    ]
    found = find(results, text)
    assert ("PESSOA", "Kawanny Prates", 0.72) in found or ("PESSOA", "Kawanny Prates", 0.66) in found
    assert all(item[1] != "Bolota Zyx" for item in found)
    assert any(item[1] == "Maria Tal" for item in found)
    assert all(item[0] == "PESSOA" for item in found)


def test_context_corroborates():
    text = "cliente Zorbax Quintil pediu"
    found = find([{"entity_group": "B-PER", "score": 0.6, "start": 8, "end": 22}], text)
    assert found == [("PESSOA", "Zorbax Quintil", 0.72)]


def test_trims_punctuation_and_ignores_short():
    text = "Oi, (Ana)!"
    assert find([{"entity_group": "NOME", "score": 0.99, "start": 4, "end": 10}], text) == [("PESSOA", "Ana", 0.72)]
    assert find([{"entity_group": "NOME", "score": 0.99, "start": 0, "end": 2}], text) == []


def test_config_and_missing_dependency(monkeypatch, tmp_path):
    path = tmp_path / "veu.toml"
    path.write_text('[deteccao]\ndetectores = ["padroes", "ml"]\nmodelo_ml = "meu/modelo"\n', encoding="utf-8")
    config = load_config(str(path), environ={})
    assert config.ml_model == "meu/modelo" and "ml" in config.detectors
    import builtins

    real_import = builtins.__import__

    def no_transformers(name, *args, **kwargs):
        if name == "transformers":
            raise ImportError("sem transformers")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_transformers)
    with pytest.raises(RuntimeError, match=r"veu\[ml\]"):
        Veu(config)


def test_unknown_detector_still_rejected():
    with pytest.raises(ConfigError):
        load_config(None, environ={"VEU_DETECTORES": "padroes,inventado"})


def test_long_texts_are_split_when_the_tokenizer_has_no_limit(monkeypatch):
    """Alguns modelos não informam o limite no tokenizador; sem ele, a pipeline não divide o texto e quebra."""
    import sys
    import types

    built = {}

    def pipeline(task, **kwargs):
        tokenizer = types.SimpleNamespace(model_max_length=int(1e30))
        model = types.SimpleNamespace(config=types.SimpleNamespace(max_position_embeddings=512))
        built.update(kwargs, tokenizer=tokenizer)
        return types.SimpleNamespace(tokenizer=tokenizer, model=model)

    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(pipeline=pipeline))
    MLRecognizer("meu/modelo")
    assert built["tokenizer"].model_max_length == 512
    assert built["stride"] > 0 and built["aggregation_strategy"] == "simple"
