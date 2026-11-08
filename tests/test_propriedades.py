"""Testes de propriedade (hypothesis): ida e volta, streaming igual ao lote e leitura de SSE em qualquer corte."""

import json
import os

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from veu import Veu  # noqa: E402
from veu.gateway.sse import NDJSONTransformer, SSETransformer, encode_event  # noqa: E402
from veu.vault import RestorePolicy, Vault  # noqa: E402

veu = Veu(link_names=False)
# Valores distintos (cada um aparece uma vez): ida e volta tem de devolver exatamente o texto original.
VALUES = [
    "529.982.247-25", "111.444.777-35", "11.222.333/0001-81", "(11) 98765-4321", "+1 415 555 2671",
    "maria.souza@example.com", "joao@example.org", "4111 1111 1111 1111", "DE89 3704 0044 0532 0130 00",
    "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d", "192.0.2.44",
]
# Texto de enchimento sem dígitos, colchetes, barras nem "w" (que formariam números, marcadores ou links).
FILLER = st.text(alphabet="abcdefghijklmnopqrstuvxyz ,.;:!?\n", max_size=40)
# VEU_HIPOTESES=5000 pytest tests/test_propriedades.py para uma busca longa.
FAST = settings(max_examples=int(os.environ.get("VEU_HIPOTESES", "150")), deadline=None,
                suppress_health_check=[HealthCheck.too_slow])


@FAST
@given(st.lists(st.tuples(FILLER, st.sampled_from(range(len(VALUES)))), max_size=8, unique_by=lambda item: item[1]),
       FILLER)
def test_anonymize_then_restore_is_identity(pieces, tail):
    text = "".join(filler + " " + VALUES[index] + " " for filler, index in pieces) + tail
    result = veu.anonymize(text)
    for index in {index for _, index in pieces}:
        assert VALUES[index] not in result.text or index in (10,)  # o IP de documentação não é detectado sempre
    assert result.restore(result.text) == text


def vault_with_entries() -> Vault:
    vault = Vault(policy=RestorePolicy())
    vault.placeholder("CPF", "529.982.247-25")
    vault.placeholder("PESSOA", "Maria Souza")
    vault.placeholder("CHAVE_API", "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d")
    return vault


TOKENS = st.sampled_from([
    "[CPF_1]", "[PESSOA_1]", "[CHAVE_API_1]", "CPF_1", "[CPF 1]", "[cpf_1]", "[PESSOA_9]", "![x](https://e.tld/?d=",
    "](", ")", "https://", "www.", "\n", " ", "texto", "[", "]", "_", "-", ":", "/", "<img src=\"", "\"", "mailto:",
    "\\/", "\\u002f", "PESS", "OA_1]",
])


@FAST
@given(st.lists(TOKENS, max_size=30), st.lists(st.integers(min_value=0, max_value=400), max_size=6),
       st.booleans())
def test_streaming_equals_batch_for_any_split(tokens, cuts, json_escape):
    text = "".join(tokens)
    vault = vault_with_entries()
    expected = vault.restore(text, json_escape=json_escape)
    points = sorted({cut % (len(text) + 1) for cut in cuts})
    chunks = [text[a:b] for a, b in zip([0, *points], [*points, len(text)], strict=True)]
    restorer = vault.restorer(json_escape=json_escape)
    assert "".join(restorer.feed(chunk) for chunk in chunks) + restorer.flush() == expected


EVENT_DATA = st.one_of(
    st.dictionaries(st.sampled_from(["type", "delta", "text", "index"]),
                    st.one_of(st.text(max_size=20), st.integers(0, 9)), max_size=3),
    st.just("[DONE]"),
)
EVENTS = st.lists(st.tuples(st.one_of(st.none(), st.sampled_from(["message", "content_block_delta"])), EVENT_DATA),
                  min_size=1, max_size=8)


def identity(name, data):
    return [(name, data)]


def parse(stream: bytes) -> list:
    events = []
    for block in stream.decode().split("\n\n"):
        if not block.strip():
            continue
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        raw = "\n".join(data)
        try:
            events.append((name, json.loads(raw)))
        except ValueError:
            events.append((name, raw))
    return events


@FAST
@given(EVENTS, st.lists(st.integers(min_value=0, max_value=2000), max_size=8), st.booleans())
def test_sse_survives_any_byte_split(events, cuts, crlf):
    stream = "".join(encode_event(name, data) for name, data in events)
    if crlf:
        stream = stream.replace("\n", "\r\n")
    raw = stream.encode()
    points = sorted({cut % (len(raw) + 1) for cut in cuts})  # inclusive no meio de um caractere UTF-8
    chunks = [raw[a:b] for a, b in zip([0, *points], [*points, len(raw)], strict=True)]
    transformer = SSETransformer(identity, list)
    output = b"".join(transformer.feed(chunk) for chunk in chunks) + transformer.close()
    assert parse(output) == events


@FAST
@given(st.binary(max_size=300), st.lists(st.integers(min_value=0, max_value=300), max_size=5))
def test_parsers_never_crash_on_garbage(data, cuts):
    points = sorted({cut % (len(data) + 1) for cut in cuts})
    chunks = [data[a:b] for a, b in zip([0, *points], [*points, len(data)], strict=True)]
    for transformer in (SSETransformer(identity, list), NDJSONTransformer(identity, list)):
        for chunk in chunks:
            transformer.feed(chunk)
        transformer.close()
