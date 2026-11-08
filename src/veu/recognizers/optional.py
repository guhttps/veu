"""Detectores opcionais: spaCy (NER), um modelo BERT (transformers) e um modelo de linguagem local (Ollama...)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from urllib.parse import urlparse

from veu._text import fold, words_regex
from veu.recognizers.base import Candidate, text_before

logger = logging.getLogger(__name__)


class SpacyRecognizer:
    """Nomes de pessoas pelo reconhecimento de entidades do spaCy (pip install "veu[spacy]")."""

    name = "spacy"
    labels = frozenset({"PESSOA"})

    def __init__(self, model: str = "pt_core_news_lg", nlp=None):
        if nlp is None:
            try:
                import spacy
            except ImportError as exc:
                raise RuntimeError('O detector "spacy" precisa do pacote spaCy: pip install "veu[spacy]"') from exc
            try:
                nlp = spacy.load(model, disable=["parser", "lemmatizer", "morphologizer", "attribute_ruler"])
            except OSError as exc:
                raise RuntimeError(
                    f'Modelo do spaCy "{model}" não encontrado. Instale com: python -m spacy download {model}'
                ) from exc
        self.nlp = nlp

    def find(self, text: str) -> Iterable[Candidate]:
        for entity in self.nlp(text).ents:
            if entity.label_ in ("PER", "PERSON") and len(entity.text.strip()) > 2:
                yield Candidate("PESSOA", entity.start_char, entity.end_char, 0.7, self.name)


class MLRecognizer:
    """Nomes por um modelo BERT de reconhecimento de entidades, rodando na sua máquina (pip install "veu[ml]").

    Padrão: linc42/pii-ner-pt-br-bertimbau (MIT), treinado em português do Brasil. Só os nomes do modelo são usados:
    documentos com dígito verificador, as regras do Véu acham melhor. Para não esconder palavras comuns, um nome do
    modelo só conta com confiança alta ou quando é corroborado (uma palavra dele está nas listas de nomes do IBGE, ou
    há contexto como "cliente" ou "Sr." por perto).
    """

    name = "ml"
    labels = frozenset({"PESSOA"})
    NAME_GROUPS = frozenset({"NOME", "PER", "PERSON", "PESSOA", "NAME"})

    def __init__(self, model: str = "linc42/pii-ner-pt-br-bertimbau", pipeline=None, min_score: float = 0.9):
        if pipeline is None:
            try:
                from transformers import pipeline as hf_pipeline
            except ImportError as exc:
                raise RuntimeError('O detector "ml" precisa do transformers e do torch: pip install "veu[ml]"') from exc
            # stride: textos maiores que o limite do modelo (512 tokens) são lidos em janelas sobrepostas.
            pipeline = hf_pipeline("token-classification", model=model, aggregation_strategy="simple", stride=128)
            # Alguns modelos não informam o limite no tokenizador; sem ele, a pipeline não divide o texto e falha.
            limit = getattr(pipeline.model.config, "max_position_embeddings", 512)
            if not 0 < (pipeline.tokenizer.model_max_length or 0) <= limit:
                pipeline.tokenizer.model_max_length = limit
        self.pipeline = pipeline
        self.min_score = min_score
        from veu.recognizers.base import folded_set
        from veu.recognizers.persons import PERSON_CONTEXT

        ambiguous = folded_set("ambiguous.txt") | folded_set("ibge_ambiguos.txt")
        self._names = (folded_set("first_names.txt") | folded_set("ibge_prenomes.txt") | folded_set("surnames.txt")
                       | folded_set("ibge_sobrenomes.txt")) - ambiguous
        self._context = words_regex(PERSON_CONTEXT)

    def find(self, text: str) -> Iterable[Candidate]:
        if not text.strip():
            return
        for item in self.pipeline(text):
            group = str(item.get("entity_group") or item.get("entity") or "").upper()
            group = group[2:] if group[:2] in ("B-", "I-") else group
            if group not in self.NAME_GROUPS:
                continue
            start, end = int(item["start"]), int(item["end"])
            while start < end and not text[start].isalnum():
                start += 1
            while end > start and not text[end - 1].isalnum():
                end -= 1
            if end - start < 3:
                continue
            score = float(item.get("score", 0))
            words = [fold(word) for word in text[start:end].split()]
            window = fold(text_before(text, start, 30))
            corroborated = any(word in self._names for word in words) or self._context.search(window) is not None
            if score >= self.min_score or (corroborated and score >= 0.5):
                yield Candidate("PESSOA", start, end, 0.72 if corroborated else 0.66, self.name)


LLM_PROMPT = (
    "Você encontra dados pessoais em textos em português do Brasil. Responda somente com JSON no formato "
    '{"pessoas": [...], "enderecos": [...]}, copiando cada trecho exatamente como aparece no texto. '
    "Inclua nomes de pessoas (não de empresas, cidades ou marcas) e endereços residenciais ou comerciais. "
    'Se não houver nenhum, responda {"pessoas": [], "enderecos": []}.'
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}


class LLMRecognizer:
    """Nomes e endereços por um modelo de linguagem compatível com OpenAI rodando na sua máquina.

    O texto é enviado ao modelo configurado, então use um modelo local (Ollama, LM Studio, vLLM):
    mandar o texto original para um provedor externo anularia o propósito do Véu.
    """

    name = "llm"
    labels = frozenset({"PESSOA", "ENDERECO"})

    def __init__(self, url: str, model: str, api_key: str | None = None, timeout: float = 60.0, client=None):
        import httpx

        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout)
        host = urlparse(self.url).hostname or ""
        if host not in _LOCAL_HOSTS and not host.endswith(".local"):
            logger.warning(
                "O detector por IA envia o texto original para %s. Use um modelo local para não expor os dados.",
                host,
            )

    def find(self, text: str) -> Iterable[Candidate]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": LLM_PROMPT}, {"role": "user", "content": text}],
        }
        try:
            response = self.client.post(f"{self.url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # o detector é complementar: os demais continuam funcionando
            logger.warning("Detector por IA indisponível: %s", exc)
            return
        found = _parse_json(content)
        for label, key in (("PESSOA", "pessoas"), ("ENDERECO", "enderecos")):
            for snippet in found.get(key) or []:
                if not isinstance(snippet, str) or len(snippet.strip()) < 3:
                    continue
                for match in re.finditer(re.escape(snippet.strip()), text):
                    yield Candidate(label, match.start(), match.end(), 0.75, self.name)


def _parse_json(content: str) -> dict:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        parsed = json.loads(content[start:end + 1])
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
