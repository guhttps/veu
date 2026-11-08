"""Monta o site de documentação a partir do README e de docs/, sem duplicar texto.

    pip install zensical==0.1.0
    python scripts/gerar_site.py               # compila em web/docs (publicado no GitHub Pages)
    python scripts/gerar_site.py --servir      # pré-visualização em http://localhost:8000

O README é dividido em páginas pelas seções (## ...). Os links são corrigidos: âncoras do README apontam para a
página certa, docs/x.md vira x.md, e arquivos fora da documentação (exemplos, código, SECURITY.md) viram links para
o GitHub. Os avisos do GitHub (> [!NOTE]) viram caixas do site.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "site"
REPO = "https://github.com/guhttps/veu/blob/main/"
SITE_URL = "https://guhttps.github.io/veu/docs/"

# Seções do README -> página. None: a seção fica de fora porque uma página de docs/ já cobre o assunto (e as
# âncoras dela apontam para essa página).
README_PAGES = {
    "Comece por aqui": "index.md",
    "Instalar sem saber programar": "instalar.md",
    "Recursos": "recursos.md",
    "Como funciona": "recursos.md",
    "Para programadores": "programadores.md",
    "Integrações": None,
    "O que é detectado": "deteccao.md",
    "Operadores": "deteccao.md",
    "Benchmark": None,
    "Configuração": "configuracao.md",
    "Segurança": "seguranca.md",
    "Desenvolvimento": "contribuir.md",
    "Próximos passos": "contribuir.md",
    "Licença": "contribuir.md",
}
SECTION_REPLACED_BY = {"Integrações": "integracoes.md", "Benchmark": "benchmark.md"}
PAGE_TITLES = {
    "instalar.md": "Instalar sem saber programar", "recursos.md": "Recursos", "programadores.md": "Para programadores",
    "deteccao.md": "O que é detectado", "configuracao.md": "Configuração", "seguranca.md": "Segurança",
    "contribuir.md": "Desenvolvimento",
}
# Outros arquivos do repositório que viram páginas.
EXTRA_PAGES = {"js/README.md": "javascript.md", "n8n/README.md": "n8n.md"}

NAV = [
    ("Início", "index.md"),
    ("Começar", [("Instalar sem programar", "instalar.md"), ("Recursos", "recursos.md"), ("Extensão", "extensao.md")]),
    ("Programadores", [("Python, proxy e comandos", "programadores.md"), ("JavaScript", "javascript.md"),
                       ("Integrações", "integracoes.md"), ("n8n", "n8n.md"), ("Configuração", "configuracao.md")]),
    ("Empresas", [("Guia para empresas", "empresas.md"), ("Conformidade (LGPD)", "conformidade.md"),
                  ("Modelo de RIPD", "modelo-ripd.md")]),
    ("Detecção", [("O que é detectado", "deteccao.md"), ("Benchmark", "benchmark.md")]),
    ("Segurança", [("Segurança", "seguranca.md"), ("Modelo de ameaças", "modelo-de-ameacas.md")]),
    ("Contribuir", "contribuir.md"),
]


def github_slug(heading: str) -> str:
    """Âncora que o GitHub gera para um título (mantém acentos)."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower().replace("`", ""))
    return text.replace(" ", "-")


def site_slug(heading: str) -> str:
    """Âncora que o site gera (Python-Markdown): sem acentos, hífens repetidos viram um."""
    text = unicodedata.normalize("NFKD", heading.replace("`", "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def headings(markdown: str) -> list[tuple[int, str]]:
    """Títulos (nível, texto), ignorando os que estão dentro de blocos de código."""
    found, fenced = [], False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (match := re.match(r"(#{1,6}) (.+)", line)):
            found.append((len(match.group(1)), match.group(2).strip()))
    return found


def split_readme(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Separa a introdução (antes do primeiro ##) e as seções de nível 2, fora de blocos de código."""
    sections, current, buffer, intro, fenced = [], None, [], [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if current is not None:
                sections.append((current, "".join(buffer)))
            current, buffer = line[3:].strip(), []
            continue
        (buffer if current is not None else intro).append(line)
    if current is not None:
        sections.append((current, "".join(buffer)))
    return "".join(intro), sections


class Linker:
    """Reescreve links relativos do repositório para o site."""

    def __init__(self, readme_anchors: dict[str, str], page_anchors: dict[str, dict[str, str]],
                 file_pages: dict[str, str]):
        self.readme_anchors = readme_anchors  # âncora do GitHub no README -> "pagina.md#ancora-do-site"
        self.page_anchors = page_anchors      # página -> {âncora do GitHub: âncora do site}
        self.file_pages = file_pages          # caminho no repositório -> página do site

    def target(self, link: str, source: str) -> str:
        if re.match(r"[a-z]+:", link) or link.startswith("//"):
            return link
        path, _, anchor = link.partition("#")
        if not path:  # âncora na mesma origem
            if source == "README.md":
                return self.readme_anchors.get(anchor, f"#{site_slug(anchor)}")
            page = self.file_pages.get(source, "")
            return f"#{self.page_anchors.get(page, {}).get(anchor, site_slug(anchor))}"
        resolved = (Path(source).parent / path).as_posix()
        resolved = re.sub(r"(^|/)[^/]+/\.\./", r"\1", resolved)
        while "/../" in resolved or resolved.startswith("../"):
            resolved = re.sub(r"[^/]+/\.\./", "", resolved, count=1)
            if resolved.startswith("../"):
                resolved = resolved[3:]
        resolved = resolved.removeprefix("./")
        if resolved == "README.md":
            return self.readme_anchors.get(anchor, "index.md") if anchor else "index.md"
        if resolved in self.file_pages:
            page = self.file_pages[resolved]
            if not anchor:
                return page
            return f"{page}#{self.page_anchors.get(page, {}).get(anchor, site_slug(anchor))}"
        if resolved.startswith("docs/") and resolved.endswith((".png", ".svg", ".jpg")):
            return resolved.removeprefix("docs/")
        return REPO + resolved + (f"#{anchor}" if anchor else "")

    def rewrite(self, markdown: str, source: str) -> str:
        out, fenced = [], False
        for line in markdown.splitlines(keepends=True):
            if line.lstrip().startswith("```"):
                fenced = not fenced
            if fenced or line.lstrip().startswith("```"):
                out.append(line)
                continue
            line = re.sub(r"\]\(([^)\s]+)\)", lambda m: f"]({self.target(m.group(1), source)})", line)
            line = re.sub(r'(src|href)="([^"]+)"', lambda m: f'{m.group(1)}="{self.target(m.group(2), source)}"', line)
            out.append(line)
        return "".join(out)


ALERTS = {"NOTE": ("note", "Nota"), "TIP": ("tip", "Dica"), "IMPORTANT": ("important", "Importante"),
          "WARNING": ("warning", "Atenção"), "CAUTION": ("danger", "Cuidado")}


def convert_alerts(markdown: str) -> str:
    """> [!NOTE] do GitHub vira !!! note do site."""
    lines, out, index = markdown.splitlines(), [], 0
    while index < len(lines):
        match = re.match(r">\s*\[!(\w+)\]\s*$", lines[index])
        if match and match.group(1) in ALERTS:
            body, index = [], index + 1
            while index < len(lines) and lines[index].startswith(">"):
                body.append(lines[index][1:].removeprefix(" "))
                index += 1
            kind, title = ALERTS[match.group(1)]
            out.append(f'!!! {kind} "{title}"')
            out.extend(f"    {line}" if line else "" for line in body)
            continue
        out.append(lines[index])
        index += 1
    return "\n".join(out) + "\n"


def readme_intro(intro: str) -> str:
    """Introdução do README sem os selos; o banner vira uma imagem comum."""
    intro = re.sub(r'<p align="center">\s*<img src="docs/banner.png"[^>]*>\s*</p>', "![Véu](docs/banner.png)", intro)
    return re.sub(r'<p align="center">.*?</p>\s*', "", intro, flags=re.S)


def toml_nav(entries) -> str:
    def item(title, target):
        if isinstance(target, str):
            return f'{{ "{title}" = "{target}" }}'
        return f'{{ "{title}" = [{", ".join(item(t, p) for t, p in target)}] }}'

    return "nav = [\n" + ",\n".join(f"  {item(title, target)}" for title, target in entries) + ",\n]"


CONFIG = """[project]
site_name = "Véu"
site_description = "Esconde dados pessoais e segredos antes de o texto chegar à IA e devolve os dados reais na resposta."
site_url = "{site_url}"
repo_url = "https://github.com/guhttps/veu"
repo_name = "guhttps/veu"
edit_uri = "edit/main/docs/"
copyright = "Véu, código aberto (MIT)"
{nav}

[project.theme]
language = "pt-BR"
features = ["content.code.copy", "content.tabs.link", "navigation.footer", "navigation.indexes", "navigation.instant",
            "navigation.path", "navigation.sections", "navigation.top", "navigation.tracking", "search.highlight"]

[[project.theme.palette]]
media = "(prefers-color-scheme)"
toggle.icon = "lucide/sun-moon"
toggle.name = "Usar o tema claro"

[[project.theme.palette]]
media = "(prefers-color-scheme: light)"
scheme = "default"
toggle.icon = "lucide/sun"
toggle.name = "Usar o tema escuro"

[[project.theme.palette]]
media = "(prefers-color-scheme: dark)"
scheme = "slate"
toggle.icon = "lucide/moon"
toggle.name = "Seguir o sistema"

[project.markdown_extensions]
abbr = {{}}
admonition = {{}}
attr_list = {{}}
def_list = {{}}
footnotes = {{}}
md_in_html = {{}}
tables = {{}}
toc.permalink = true
pymdownx.details = {{}}
pymdownx.highlight = {{}}
pymdownx.inlinehilite = {{}}
pymdownx.superfences = {{}}
pymdownx.tasklist.custom_checkbox = true
"""


def build_sources(target: Path) -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    intro, sections = split_readme(readme)

    # Âncoras do README (como o GitHub as gera) -> página e âncora do site.
    readme_anchors: dict[str, str] = {}
    for title, body in sections:
        page = README_PAGES.get(title, "contribuir.md") or SECTION_REPLACED_BY[title]
        readme_anchors[github_slug(title)] = page if README_PAGES.get(title) is None else f"{page}#{site_slug(title)}"
        if README_PAGES.get(title):
            for _, heading in headings(body):
                readme_anchors[github_slug(heading)] = f"{page}#{site_slug(heading)}"

    file_pages = {f"docs/{path.name}": path.name for path in (ROOT / "docs").glob("*.md")}
    file_pages.update(EXTRA_PAGES)
    page_anchors: dict[str, dict[str, str]] = {}
    for source, page in file_pages.items():
        text = (ROOT / source).read_text(encoding="utf-8")
        page_anchors[page] = {github_slug(h): site_slug(h) for _, h in headings(text)}
    linker = Linker(readme_anchors, page_anchors, file_pages)

    pages: dict[str, list[str]] = {}
    pages["index.md"] = [readme_intro(intro)]
    for title, body in sections:
        page = README_PAGES.get(title, "contribuir.md")
        if page is None:
            continue
        if page not in pages:
            pages[page] = [] if page == "index.md" else [f"# {PAGE_TITLES[page]}\n\n"]
        heading = "##" if page == "index.md" or PAGE_TITLES.get(page) != title else None
        pages[page].append(f"{heading} {title}\n{body}" if heading else body)

    target.mkdir(parents=True, exist_ok=True)
    written = []
    for page, parts in pages.items():
        text = convert_alerts(linker.rewrite("".join(parts), "README.md"))
        (target / page).write_text(text, encoding="utf-8", newline="\n")
        written.append(page)
    for source, page in file_pages.items():
        text = convert_alerts(linker.rewrite((ROOT / source).read_text(encoding="utf-8"), source))
        (target / page).write_text(text, encoding="utf-8", newline="\n")
        written.append(page)
    for image in (ROOT / "docs").glob("*.png"):
        shutil.copyfile(image, target / image.name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--saida", default=str(ROOT / "web" / "docs"), help="pasta do site pronto (padrão: web/docs)")
    parser.add_argument("--servir", action="store_true", help="abre uma pré-visualização local")
    parser.add_argument("--so-fontes", action="store_true", help="só gera os .md e o zensical.toml em build/site")
    args = parser.parse_args(argv)

    shutil.rmtree(BUILD, ignore_errors=True)
    pages = build_sources(BUILD / "docs")
    missing = [page for _, target in NAV for page in ([target] if isinstance(target, str) else [p for _, p in target])
               if page not in pages]
    if missing:
        print(f"Páginas do menu sem conteúdo: {', '.join(missing)}", file=sys.stderr)
        return 1
    (BUILD / "zensical.toml").write_text(CONFIG.format(site_url=SITE_URL, nav=toml_nav(NAV)), encoding="utf-8",
                                         newline="\n")
    if args.so_fontes:
        print(f"{BUILD.relative_to(ROOT)}: {len(pages)} páginas")
        return 0
    command = [sys.executable, "-m", "zensical", "serve" if args.servir else "build"]
    if subprocess.run(command, cwd=BUILD).returncode:
        return 1
    if not args.servir:
        output = Path(args.saida)
        shutil.rmtree(output, ignore_errors=True)
        shutil.copytree(BUILD / "site", output, dirs_exist_ok=True)
        print(f"{output}: {len(pages)} páginas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
