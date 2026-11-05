"""Detector de endereços: logradouro, nome, número e complemento."""

from __future__ import annotations

import re
from collections.abc import Iterable

from veu._text import words_regex
from veu.recognizers.base import Candidate, context_window

# Logradouros que aceitam qualquer caixa ("rua", "RUA") e os que só contam com maiúscula,
# porque também são palavras comuns ("via WhatsApp", "vila").
_KEYWORD_ANY_CASE = (
    r"Rua|R\.|Avenida|Av\.?|Travessa|Trav\.|Tv\.|Alameda|Al\.|Pra[çc]a|P[çc]a\.|Rodovia|Rod\.|Estrada|"
    r"Estr\.|Viela|Beco|Ladeira|Servid[ãa]o"
)
_KEYWORD = rf"(?:(?i:{_KEYWORD_ANY_CASE})|Largo|Passagem|Vila|Via)"
_ABBREVIATION = r"(?:Dr|Dra|Prof|Profa|Gen|Cel|Mal|Pres|Eng|Sen|Dep|Gov|Cap|Ten|Sta|Sto|Pe|Frei|Dom|S)\."
_WORD = r"[A-ZÀ-Ý][\wÀ-ÿ'’-]*"
_NAME_PART = rf"(?:{_ABBREVIATION}|{_WORD})"
_FIRST = rf"(?:(?:d[aeo]s?\s+)?(?:\d{{1,3}}\s+(?:de\s+)?{_WORD}|{_NAME_PART}))"
_NEXT = rf"(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_NAME_PART})"
_NUMBER = r"(?:\s*,\s*|\s+)(?:(?:n[º°o]\.?|n\.|número)\s*)?(?:\d{1,6}[A-Za-z]?|[Ss]/[Nn])(?![\w/])"
_COMPLEMENT = (
    r"(?:\s*[,–-]?\s*(?i:apto?\.?|apartamento|ap\.|bloco|bl\.|casa|cs\.|sala|sl\.|lote|lt\.|quadra|qd\.|"
    r"conjunto|cj\.|andar|loja|torre|fundos|frente)(?:\s*[\w-]{1,6})?(?![\w]))"
)

_CAPITALIZED = re.compile(
    rf"(?<![\w]){_KEYWORD}\s+{_FIRST}{_NEXT}{{0,6}}(?P<number>{_NUMBER})?(?:{_COMPLEMENT}){{0,3}}"
)
# "moro na rua das flores 123": nomes em minúsculas só contam com número.
_LOWERCASE = re.compile(
    r"(?<![\w])(?:rua|avenida|av\.?|travessa|alameda|pra[çc]a|estrada)\s+(?:[a-zà-ÿ]+\s+){1,5}?"
    r"(?:n[º°o]\.?\s*)?\d{1,6}(?![\w])" + rf"(?:{_COMPLEMENT}){{0,3}}"
)

ADDRESS_CONTEXT = (
    "moro", "mora", "moramos", "resido", "reside", "residente", "domiciliado", "domiciliada", "endereco",
    "entrega", "entregar", "enviar para", "envio para", "localizado", "localizada", "situado", "situada",
    "sede", "fica na", "fica no", "cobranca", "imovel",
)


class AddressRecognizer:
    name = "enderecos"
    labels = frozenset({"ENDERECO"})

    def __init__(self):
        self._context = words_regex(ADDRESS_CONTEXT)

    def find(self, text: str) -> Iterable[Candidate]:
        for match in _CAPITALIZED.finditer(text):
            end = match.end()
            # Não termina em vírgula ou espaço que o padrão de número possa ter deixado.
            while end > match.start() and text[end - 1] in " ,":
                end -= 1
            if match.group("number"):
                score = 0.9
            else:
                window = context_window(text, match.start(), end, 40, 0)
                score = 0.75 if self._context.search(window) else 0.45
            yield Candidate("ENDERECO", match.start(), end, score, self.name)
        for match in _LOWERCASE.finditer(text):
            yield Candidate("ENDERECO", match.start(), match.end(), 0.7, self.name)
