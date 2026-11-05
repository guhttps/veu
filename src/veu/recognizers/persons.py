"""Detector de nomes de pessoas por listas de nomes brasileiros e regras de contexto.

Não depende de modelos de linguagem: combina listas de primeiros nomes e sobrenomes,
a capitalização e palavras ao redor ("Sr.", "cliente", "meu nome é"...).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from veu._text import fold, words_regex
from veu.recognizers.base import Candidate, folded_set, load_wordlist

_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿ]+)*")
_SPACE_GAP = re.compile(r"[ \t]{1,2}")
CONNECTORS = frozenset({"da", "de", "do", "das", "dos", "e", "del", "della", "di", "du", "van", "von", "der", "d"})

PERSON_CONTEXT = (
    "sr", "sr.", "sra", "sra.", "srta", "senhor", "senhora", "dona", "dom", "seu", "dr", "dr.", "dra", "dra.",
    "doutor", "doutora", "prof", "prof.", "profa", "professor", "professora", "cliente", "paciente", "aluno",
    "aluna", "nome", "nome completo", "chamo", "chama", "chamado", "chamada", "prezado", "prezada", "caro", "cara",
    "querido", "querida", "oi", "ola", "atenciosamente", "att", "cordialmente", "assinado", "assinatura",
    "titular", "responsavel", "contratante", "contratado", "contratada", "locador", "locadora", "locatario",
    "locataria", "fiador", "fiadora", "autor", "autora", "reu", "requerente", "requerido", "requerida",
    "testemunha", "advogado", "advogada", "funcionario", "funcionaria", "colaborador", "colaboradora", "colega",
    "filho", "filha", "mae", "pai", "esposa", "esposo", "marido", "irmao", "irma", "avo", "neto", "neta", "tio",
    "tia", "sobrinho", "sobrinha", "amigo", "amiga", "vizinho", "vizinha", "motorista", "entregador",
    "entregadora", "atendente", "medico", "medica", "enfermeiro", "enfermeira", "falar com", "aos cuidados de",
    "a/c", "de:", "para:", "por", "com o", "com a", "pelo", "pela", "segurado", "segurada", "beneficiario",
    "beneficiaria", "dependente", "candidato", "candidata", "inquilino", "inquilina", "proprietario",
    "proprietaria", "comprador", "compradora", "vendedor", "vendedora", "destinatario", "remetente",
)
# Palavras que indicam empresa, órgão ou estabelecimento: a sequência não é um nome de pessoa.
ORGANIZATION_WORDS = frozenset({
    "ltda", "ltd", "s.a", "sa", "me", "eireli", "epp", "mei", "cia", "companhia", "hospital", "clinica",
    "farmacia", "drogaria", "padaria", "mercado", "supermercado", "mercearia", "construtora", "incorporadora",
    "escola", "colegio", "faculdade", "universidade", "instituto", "fundacao", "associacao", "cooperativa",
    "sindicato", "banco", "grupo", "empresa", "industria", "industrias", "comercio", "distribuidora",
    "transportadora", "logistica", "consultoria", "tecnologia", "solucoes", "servicos", "sistemas", "restaurante",
    "lanchonete", "pizzaria", "hotel", "pousada", "academia", "loja", "lojas", "magazine", "atacadao", "posto",
    "auto", "pecas", "imobiliaria", "advocacia", "advogados", "associados", "contabilidade", "laboratorio",
    "odontologia", "studio", "estudio", "agencia", "editora", "igreja", "paroquia", "prefeitura", "secretaria",
    "ministerio", "tribunal", "assembleia", "hub", "tech", "digital", "software", "games", "foods",
})
# Aplicado ao texto normalizado por fold(), que remove o espaço final.
_STREET_BEFORE = re.compile(
    r"(?<![\w])(?:rua|r\.|av\.?|avenida|travessa|tv\.|alameda|al\.|praca|pca\.|rodovia|rod\.|estrada|largo|viela|"
    r"beco|ladeira|vila|bairro|jardim|parque|condominio|edificio|residencial)(?:\s+d[aeo]s?)?\s*$"
)
GREETINGS = (
    "oi", "ola", "e ai", "eai", "fala", "bom dia", "boa tarde", "boa noite", "obrigado", "obrigada", "valeu",
    "vlw", "tchau", "beijo", "bjs", "abraco", "querido", "querida", "meu nome e", "me chamo", "sou o", "sou a",
    "aqui e o", "aqui e a", "com o", "com a",
)


class PersonRecognizer:
    name = "nomes"
    labels = frozenset({"PESSOA"})

    def __init__(self, extra_first_names: Iterable[str] = (), extra_surnames: Iterable[str] = ()):
        self.first_names = folded_set("first_names.txt") | {fold(name) for name in extra_first_names}
        self.surnames = folded_set("surnames.txt") | {fold(name) for name in extra_surnames}
        self.ambiguous = folded_set("ambiguous.txt")
        self.stopwords = folded_set("stopwords.txt")
        # Palavras comuns que, sem acento, viram nomes ("Março" x "Marco") só contam com o acento exato.
        self._stop_exact = {word.casefold() for word in load_wordlist("stopwords.txt")}
        self._stop_folded = self.stopwords - self.first_names - self.surnames
        self.places = folded_set("places.txt")
        self.organizations = folded_set("organizations.txt")
        self._context = words_regex(PERSON_CONTEXT)
        self._greeting = re.compile(
            r"(?:^|[^\w])(?:" + "|".join(re.escape(fold(g)) for g in GREETINGS) + r")[\s,!]*$"
        )

    def _is_name_word(self, word: str) -> bool:
        folded = fold(word)
        return folded in self.first_names or folded in self.surnames

    def _is_stop(self, word: str) -> bool:
        return word.casefold() in self._stop_exact or fold(word) in self._stop_folded

    def _is_capitalized(self, word: str) -> bool:
        if not word[0].isupper():
            return False
        # Siglas curtas (SP, RG, CPF) não são nomes, mas "ANA", "EVA" e "ITO" em maiúsculas são.
        return not (word.isupper() and len(word) <= 3) or fold(word) in self.first_names or fold(word) in self.surnames

    def _has_context(self, text: str, start: int, before: int = 30) -> bool:
        window = fold(text[max(0, start - before):start])
        return self._context.search(window) is not None

    def find(self, text: str) -> Iterable[Candidate]:
        words = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]
        index = 0
        while index < len(words):
            word = words[index][2]
            if not self._is_capitalized(word) or fold(word) in CONNECTORS:
                index += 1
                continue
            sequence = [index]
            nxt = index + 1
            while nxt < len(words):
                gap = text[words[nxt - 1][1]:words[nxt][0]]
                if not _SPACE_GAP.fullmatch(gap):
                    break
                candidate = words[nxt][2]
                if fold(candidate) in CONNECTORS:
                    if (
                        nxt + 1 < len(words)
                        and _SPACE_GAP.fullmatch(text[words[nxt][1]:words[nxt + 1][0]])
                        and self._is_capitalized(words[nxt + 1][2])
                    ):
                        sequence.append(nxt)
                        nxt += 1
                        continue
                    break
                if not self._is_capitalized(candidate):
                    break
                sequence.append(nxt)
                nxt += 1
            found = self._score_sequence(text, [words[k] for k in sequence])
            if found:
                yield found
            index = sequence[-1] + 1
        yield from self._lowercase_names(text, words)

    def _score_sequence(self, text: str, tokens: list[tuple[int, int, str]]) -> Candidate | None:
        whole = [fold(token[2]) for token in tokens]
        if " ".join(whole) in self.places | self.organizations:
            return None
        if any(word in ORGANIZATION_WORDS for word in whole):
            return None
        # Começa no primeiro nome conhecido; sem nenhum, só descarta palavras comuns do início.
        first_index = next((i for i, token in enumerate(tokens) if fold(token[2]) in self.first_names), None)
        if first_index is not None:
            tokens = tokens[first_index:]
        else:
            while tokens and (self._is_stop(tokens[0][2]) or fold(tokens[0][2]) in CONNECTORS):
                tokens = tokens[1:]
        while tokens and (self._is_stop(tokens[-1][2]) or fold(tokens[-1][2]) in CONNECTORS):
            tokens = tokens[:-1]
        if not tokens:
            return None
        folded = [fold(token[2]) for token in tokens]
        joined = " ".join(folded)
        if joined in self.places or joined in self.organizations:
            return None
        start, end = tokens[0][0], tokens[-1][1]
        # "Rua Augusta", "Av. Getúlio Vargas": nome de logradouro, não de pessoa.
        if _STREET_BEFORE.search(fold(text[max(0, start - 16):start])):
            return None
        context = self._has_context(text, start)
        name_words = [token[2] for token in tokens if fold(token[2]) not in CONNECTORS]
        if len(name_words) >= 2 and any(self._is_stop(word) for word in name_words):
            return None
        name_words = [fold(word) for word in name_words]
        known_first = folded[0] in self.first_names
        known = sum(1 for word in name_words if word in self.first_names or word in self.surnames)

        if len(name_words) >= 2:
            if known_first and known >= 2:
                score = 0.9
            elif known_first:
                score = 0.8
            elif name_words[-1] in self.surnames or known >= 2:
                score = 0.7 if context else 0.62
            elif context:
                score = 0.65
            else:
                return None
        else:
            word = name_words[0]
            if self._is_stop(tokens[0][2]) or (word in self.places and word not in self.first_names):
                return None
            if word in self.first_names:
                if word in self.ambiguous:
                    if not context:
                        return None
                    score = 0.7
                else:
                    score = 0.8 if context else 0.6
            elif context and (word in self.surnames or self._strong_context(text, start)):
                score = 0.6
            else:
                return None
        return Candidate("PESSOA", start, end, score, self.name)

    def _strong_context(self, text: str, start: int) -> bool:
        window = fold(text[max(0, start - 25):start])
        return re.search(r"(?:meu nome e|me chamo|nome:|nome completo:|sr\.?|sra\.?|dona|dr\.?|dra\.?)\s*$", window) is not None

    def _lowercase_names(self, text: str, words: list[tuple[int, int, str]]) -> Iterable[Candidate]:
        """Nomes em minúsculas, comuns em conversas: "oi joao", "falei com maria souza"."""
        index = 0
        while index < len(words):
            start, end, word = words[index]
            folded = fold(word)
            if (
                not word.islower()
                or folded not in self.first_names
                or folded in self.ambiguous
                or self._is_stop(word)
                or len(folded) < 3
            ):
                index += 1
                continue
            last = index
            while (
                last + 1 < len(words)
                and words[last + 1][2].islower()
                and fold(words[last + 1][2]) in self.surnames | CONNECTORS
                and _SPACE_GAP.fullmatch(text[words[last][1]:words[last + 1][0]])
            ):
                last += 1
            while last > index and fold(words[last][2]) in CONNECTORS:
                last -= 1
            before = fold(text[max(0, start - 18):start])
            if last > index:
                yield Candidate("PESSOA", start, words[last][1], 0.65, self.name)
            elif self._greeting.search(before):
                yield Candidate("PESSOA", start, end, 0.6, self.name)
            index = last + 1
