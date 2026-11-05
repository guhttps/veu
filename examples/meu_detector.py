"""Detector próprio: matrículas no formato MAT-123456.

Ligue de um destes jeitos:
    Veu(extra_recognizers=[Matricula()])
    veu.toml:  detectores = ["padroes", "nomes", "enderecos", "meu_detector:Matricula"]
    plugin:    [project.entry-points."veu.detectores"] matricula = "meu_pacote.meu_detector:Matricula"
"""

import re

from veu.recognizers import Candidate

PADRAO = re.compile(r"\bMAT-\d{6}\b")


class Matricula:
    name = "matricula"
    labels = frozenset({"MATRICULA"})

    def find(self, text: str):
        for match in PADRAO.finditer(text):
            yield Candidate("MATRICULA", match.start(), match.end(), 0.95, self.name)


if __name__ == "__main__":
    from veu import Veu

    print(Veu(extra_recognizers=[Matricula()]).anonymize("A aluna MAT-482913 trancou o curso.").text)
