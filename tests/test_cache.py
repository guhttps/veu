"""Cache de detecção: mesmo resultado, sem guardar texto, separado por cliente e mais rápido em conversas longas."""

import asyncio
import json
import time

import httpx

from veu import Veu
from veu.analyzer import Analyzer
from veu.cache import DetectionCache, cache_scope
from veu.config import Config, load_config
from veu.server import create_app

LONG = ("Histórico do atendimento. A cliente Marina Albuquerque, CPF 529.982.247-25, ligou pedindo a segunda via "
        "do boleto e informou o telefone (11) 98765-4321 e o e-mail marina.albuquerque@example.com. ") * 3


def test_cache_returns_the_same_entities_and_counts_hits():
    cache = DetectionCache(16)
    analyzer = Analyzer(cache=cache)
    first = analyzer.analyze(LONG)
    second = analyzer.analyze(LONG)
    assert first == second and first
    assert (cache.hits, cache.misses) == (1, 1)
    assert analyzer.analyze(LONG, threshold=0.99) != first or cache.misses == 2  # outro limiar, outra chave


def test_cache_never_stores_text():
    cache = DetectionCache(16)
    Analyzer(cache=cache).analyze(LONG)
    stored = repr(list(cache._items.items()))
    assert "Marina" not in stored and "529.982.247-25" not in stored and "98765" not in stored
    assert all(len(key) == 16 for key in cache._items)


def test_short_texts_are_not_cached():
    cache = DetectionCache(16)
    Analyzer(cache=cache).analyze("CPF 529.982.247-25")
    assert len(cache) == 0 and cache.misses == 0


def test_lru_limit():
    cache = DetectionCache(2)
    analyzer = Analyzer(cache=cache)
    for index in range(5):
        analyzer.analyze(LONG + str(index))
    assert len(cache) == 2


def test_scopes_are_separate():
    cache = DetectionCache(16)
    analyzer = Analyzer(cache=cache)
    with cache_scope("cliente-a"):
        analyzer.analyze(LONG)
    with cache_scope("cliente-b"):
        analyzer.analyze(LONG)
    assert (cache.hits, cache.misses) == (0, 2)
    with cache_scope("cliente-a"):
        analyzer.analyze(LONG)
    assert cache.hits == 1


def test_config_and_disable(tmp_path):
    assert Veu().analyzer.cache is not None
    assert Veu(detection_cache=0).analyzer.cache is None
    path = tmp_path / "veu.toml"
    path.write_text("[deteccao]\ncache = 10\n", encoding="utf-8")
    assert load_config(str(path), environ={}).detection_cache == 10


def test_cache_makes_resent_conversations_faster():
    history = [LONG + f" Mensagem {index}." for index in range(40)]
    uncached = Analyzer()
    cached = Analyzer(cache=DetectionCache(256))
    for text in history:
        cached.analyze(text)
    started = time.perf_counter()
    for text in history:
        uncached.analyze(text)
    slow = time.perf_counter() - started
    started = time.perf_counter()
    for text in history:
        cached.analyze(text)
    fast = time.perf_counter() - started
    assert fast * 5 < slow


def test_proxy_partitions_the_cache_by_credential():
    seen = []

    def upstream(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"content": "ok"}}]})

    app = create_app(Config(), upstream_transport=httpx.MockTransport(upstream))
    body = {"model": "m", "messages": [{"role": "user", "content": LONG}]}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            for key in ("sk-a", "sk-a", "sk-b"):
                await c.post("/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
            return (await c.get("/veu/estatisticas")).json(), (await c.get("/veu/metricas")).text

    stats, metrics = asyncio.run(run())
    assert stats["cache_deteccao"]["acertos"] == 1 and stats["cache_deteccao"]["falhas"] == 2
    assert "veu_cache_acertos_total 1" in metrics
    assert all("529.982.247-25" not in json.dumps(item) for item in seen)
