"""Gera as listas de nomes do Véu a partir do Censo 2022 do IBGE (Nomes do Brasil).

    curl -LO https://raw.githubusercontent.com/LibreOffice/dictionaries/master/pt_BR/pt_BR.dic
    python scripts/gerar_nomes_ibge.py --dicionario pt_BR.dic

Fonte: IBGE, Censo Demográfico 2022, API de nomes (servicodados.ibge.gov.br/api/v3/nomes/2022). Dados públicos.
Os nomes vêm sem acento e em minúsculas, como o Véu compara (fold).

Saídas em src/veu/data/:
- ibge_prenomes.txt: prenomes com frequência mínima (padrão: 2.000 pessoas).
- ibge_sobrenomes.txt: sobrenomes com frequência mínima (padrão: 5.000 pessoas).
- ibge_municipios.txt: municípios do Brasil que não começam com um prenome ("Bela Vista", "Belo Jardim"). Os
  que começam ("Paulo Afonso", "Carlos Barbosa") ficam de fora: uma pessoa com esse nome tem que ser escondida.
- ibge_ambiguos.txt: prenomes e sobrenomes que também são palavras comuns ("rosa", "luz", "natal"). Eles só contam como nome
  com contexto, como os de ambiguous.txt. Palavra comum é a que aparece em minúsculas no dicionário pt_BR do
  LibreOffice (VERO, usado só aqui, na geração; não é distribuído com o Véu) ou nas listas do próprio Véu (lugares,
  organizações e palavras comuns).

As páginas da API ficam em cache (--cache) para não repetir os downloads.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "veu" / "data"
GZIP = bytes((0x1F, 0x8B))
API = "https://servicodados.ibge.gov.br/api/v3/nomes/2022/localidade/0/ranking/{kind}?page={page}"
MUNICIPALITIES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

def fetch(kind: str, minimum: int, cache: Path) -> list[tuple[str, int]]:
    cache.mkdir(parents=True, exist_ok=True)
    names: list[tuple[str, int]] = []
    page = 1
    while True:
        target = cache / f"{kind}-{page}.json"
        if target.is_file():
            data = json.loads(target.read_text(encoding="utf-8"))
        else:
            request = urllib.request.Request(API.format(kind=kind, page=page), headers={"User-Agent": "veu-dados"})
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (URL fixa do IBGE)
                raw = response.read()
            data = json.loads(gzip.decompress(raw) if raw[:2] == GZIP else raw)
            target.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.15)
        for item in data["items"]:
            if item["frequencia"] < minimum:
                return names
            names.append((item["nome"], item["frequencia"]))
        if not data.get("nextPage"):
            return names
        page += 1


def get_json(url: str, target: Path):
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    request = urllib.request.Request(url, headers={"User-Agent": "veu-dados"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (URL fixa do IBGE)
        raw = response.read()
    data = json.loads(gzip.decompress(raw) if raw[:2] == GZIP else raw)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def derived_words(words: set[str], stems: dict[str, set[str]], affix_file: Path) -> set[str]:
    """Palavras que o dicionário gera por sufixos ("nascimento" vem de "nascer"; "dores", de "dor").

    Busca ao contrário: para cada nome, as regras cuja terminação bate com o fim dele dão o verbete de origem.
    """
    from veu._text import fold

    if not affix_file.is_file():
        print(f"Sem {affix_file.name}: só os verbetes do dicionário contam como palavras.", file=sys.stderr)
        return set()
    rules: dict[str, list[tuple[str, str, re.Pattern]]] = {}
    for line in affix_file.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "SFX":
            continue
        flag, strip, add, condition = parts[1], parts[2], parts[3].split("/", 1)[0], parts[4]
        strip, add = ("" if strip == "0" else fold(strip)), ("" if add == "0" else fold(add))
        try:
            pattern = re.compile(fold(condition) + "$")
        except re.error:
            continue
        rules.setdefault(add, []).append((flag, strip, pattern))
    found = set()
    for word in words:
        for cut in range(len(word) + 1):
            for flag, strip, pattern in rules.get(word[cut:], ()):
                base = word[:cut] + strip
                if flag in stems.get(base, ()) and pattern.search(base):
                    found.add(word)
                    break
            if word in found:
                break
    return found


def wordlist(name: str) -> set[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from veu._text import fold

    lines = (DATA / name).read_text(encoding="utf-8").splitlines()
    return {fold(line) for line in lines if line.strip() and not line.startswith("#")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--prenomes", type=int, default=2000, help="frequência mínima dos prenomes")
    parser.add_argument("--sobrenomes", type=int, default=5000, help="frequência mínima dos sobrenomes")
    parser.add_argument("--dicionario", type=Path, required=True,
                        help="pt_BR.dic do LibreOffice (Hunspell), para achar prenomes que são palavras comuns")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache" / "ibge")
    args = parser.parse_args()

    first = fetch("prenome", args.prenomes, args.cache)
    last = fetch("sobrenome", args.sobrenomes, args.cache)
    # "Silva", "Santos" e "Rodrigues" também aparecem como prenomes, mas são muito mais comuns como sobrenomes:
    # contar como prenome faria o nome começar neles ("Kawanny Rodrigues" viraria só "Rodrigues").
    as_surname = dict(last)
    first = [(name, count) for name, count in first if as_surname.get(name, 0) < 10 * count]
    print(f"{len(first)} prenomes e {len(last)} sobrenomes do IBGE", file=sys.stderr)

    from veu._text import fold

    stems: dict[str, set[str]] = {}  # verbete (sem acento) -> flags das regras de afixo
    for line in args.dicionario.read_text(encoding="utf-8-sig").splitlines()[1:]:
        word, _, flags = line.strip().partition("/")
        if word and word[0].islower() and word.isalpha():
            stems.setdefault(fold(word), set()).update(flags)
    first_names = {name for name, _ in first}
    surnames = {name for name, _ in last}
    common = set(stems) | derived_words(first_names | surnames, stems, args.dicionario.with_suffix(".aff"))
    curated = wordlist("first_names.txt")
    known_words = wordlist("stopwords.txt") | wordlist("places.txt") | wordlist("organizations.txt")
    short = {name for name in first_names if len(name) <= 3}  # "tel", "cel": abreviações também
    verbs = {name for name in first_names | surnames if name + "r" in common}  # "mora" (morar), "lia" (liar)
    # Os prenomes da lista curada já foram revistos à mão: continuam valendo como estão.
    ambiguous = sorted((((common | known_words | short | verbs) & (first_names | surnames)) - curated)
                       | (wordlist("ambiguous.txt") & first_names))
    towns = []
    for town in get_json(MUNICIPALITIES, args.cache / "municipios.json"):
        words = fold(town["nome"]).split()
        if words and words[0] in (first_names | curated) - set(ambiguous):
            continue  # "Paulo Afonso", "Carlos Barbosa": pode ser uma pessoa, que tem de ser escondida
        towns.append(town["nome"])

    header = ("# Gerado por scripts/gerar_nomes_ibge.py. Fonte: IBGE, Censo Demográfico 2022, Nomes do Brasil.\n"
              "# {what}, com frequência mínima de {minimum} pessoas.\n")
    (DATA / "ibge_prenomes.txt").write_text(
        header.format(what="Prenomes", minimum=args.prenomes) + "\n".join(sorted(n for n, _ in first)) + "\n",
        encoding="utf-8", newline="\n")
    (DATA / "ibge_sobrenomes.txt").write_text(
        header.format(what="Sobrenomes", minimum=args.sobrenomes) + "\n".join(sorted(n for n, _ in last)) + "\n",
        encoding="utf-8", newline="\n")
    (DATA / "ibge_municipios.txt").write_text(
        "# Gerado por scripts/gerar_nomes_ibge.py. Fonte: IBGE, Localidades. Municípios que não começam com prenome.\n"
        + "\n".join(sorted(set(towns))) + "\n", encoding="utf-8", newline="\n")
    (DATA / "ibge_ambiguos.txt").write_text(
        "# Gerado por scripts/gerar_nomes_ibge.py: nomes do IBGE que também são palavras comuns (só valem com contexto).\n"
        + "\n".join(ambiguous) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(ambiguous)} nomes ambíguos (também são palavras), {len(set(towns))} municípios", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
