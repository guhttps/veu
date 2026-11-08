"""Site de documentação: montado do README e de docs/, com todos os links internos apontando para algo que existe."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gerar_site", ROOT / "scripts" / "gerar_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    target = tmp_path_factory.mktemp("site")
    site.build_sources(target)
    return {path.name: path.read_text(encoding="utf-8") for path in target.glob("*.md")}


def nav_pages():
    for _, target in site.NAV:
        yield from ([target] if isinstance(target, str) else [page for _, page in target])


def outside_code(markdown: str) -> str:
    return re.sub(r"```.*?```", "", markdown, flags=re.S)


def test_every_menu_page_is_generated(pages):
    assert set(nav_pages()) <= set(pages)


def test_no_repository_paths_or_github_alerts_left(pages):
    for name, text in pages.items():
        body = outside_code(text)
        # Links relativos para o repositório não existem no site (links absolutos para o GitHub podem).
        assert not re.search(r"\]\((?:\.\./|\./)?(?:docs/|README\.md)", body), name
        assert not re.search(r"^>\s*\[!\w+\]", body, flags=re.M), name


def test_internal_links_point_to_existing_pages_and_anchors(pages):
    anchors = {name: {site.site_slug(h) for _, h in site.headings(text)} for name, text in pages.items()}
    broken = []
    for name, text in pages.items():
        for link in re.findall(r"\]\(([^)\s]+)\)", outside_code(text)):
            if re.match(r"[a-z]+:", link) or link.endswith((".png", ".gif")):
                continue
            page, _, anchor = link.partition("#")
            page = page or name
            if page not in pages or (anchor and anchor not in anchors[page]):
                broken.append(f"{name}: {link}")
    assert not broken


def test_slugs():
    assert site.github_slug("O que é detectado") == "o-que-é-detectado"
    assert site.site_slug("O que é detectado") == "o-que-e-detectado"
    assert site.site_slug("Python 3.11 a 3.14 (já) -- ok") == "python-311-a-314-ja-ok"


def test_alerts_become_admonitions():
    assert site.convert_alerts("> [!NOTE]\n> texto\n\nfim") == '!!! note "Nota"\n    texto\n\nfim\n'
