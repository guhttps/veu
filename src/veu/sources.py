"""Fontes externas lidas como texto: Notion, Google Docs/Sheets/Slides, páginas web e documentos.

O conteúdo é lido na sua máquina e anonimizado antes de chegar à IA:

    veu ler https://app.notion.com/p/Minha-pagina-1f2e...      # NOTION_TOKEN no ambiente
    veu ler https://docs.google.com/spreadsheets/d/.../edit    # público pelo link ou GOOGLE_ACCESS_TOKEN
    veu ler contrato.docx

Também é usado pela ferramenta MCP ler_protegido e pelo proxy (expandir_links). Usa só a biblioteca padrão.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from veu import __version__
from veu.documents import EXTENSIONS as DOCUMENT_EXTENSIONS
from veu.documents import read_document

MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = 20.0
NOTION_VERSION = "2022-06-28"
USER_AGENT = f"veu/{__version__} (+https://github.com/guhttps/veu)"
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".log", ".xml", ".html", ".htm", ".yml", ".yaml"}


class SourceError(Exception):
    """Fonte que não deu para ler (sem permissão, não encontrada, formato desconhecido)."""


@dataclass
class Document:
    source: str
    title: str
    text: str
    kind: str
    # Valores que a própria fonte diz serem dados pessoais (no Notion: propriedades do tipo pessoa, "criado por" e
    # menções a usuários). São escondidos mesmo quando a detecção automática não os reconheceria ("gustavo. Cunha").
    known: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"fonte": self.source, "titulo": self.title, "tipo": self.kind, "texto": self.text}


def replace_known(text: str, known: dict[str, str], anonymizer, vault, counts: Counter | None = None) -> str:
    """Troca os valores conhecidos (do maior para o menor) respeitando o operador configurado."""
    for value in sorted(known, key=len, reverse=True):
        if value.strip() and value in text:
            if counts is not None:
                counts[known[value]] += text.count(value)
            text = text.replace(value, anonymizer.replace_value(known[value], value, vault))
    return text


def protect_document(document: Document, anonymizer, vault) -> tuple[str, str, Counter]:
    """Título e texto protegidos (valores conhecidos da fonte + detecção) e as contagens por tipo."""
    counts: Counter = Counter()

    def protect(text: str) -> str:
        if not text:
            return text
        result = anonymizer.anonymize(replace_known(text, document.known, anonymizer, vault, counts), vault)
        counts.update(result.counts())
        return result.text

    return protect(document.title), protect(document.text), counts


# HTTP ---------------------------------------------------------------------------------------------------------------

def http(url: str, *, method: str = "GET", headers: dict | None = None, body: dict | None = None,
         timeout: float = TIMEOUT, max_bytes: int = MAX_BYTES) -> tuple[bytes, str]:
    """GET ou POST com limite de tamanho. Devolve (corpo, content-type). Levanta SourceError com mensagem clara."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "User-Agent": USER_AGENT, **({"Content-Type": "application/json"} if data else {}), **(headers or {}),
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (só http e https, abaixo)
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise SourceError(f"Conteúdo maior que {max_bytes // (1024 * 1024)} MB.")
            return content, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(ValueError, AttributeError, OSError):
            detail = json.loads(exc.read(20_000)).get("message", "")
        raise SourceError(f"HTTP {exc.code} ao ler {_safe_url(url)}" + (f": {detail}" if detail else "")) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SourceError(f"Não foi possível acessar {_safe_url(url)}: {reason}") from exc


def _safe_url(url: str) -> str:
    """URL sem a query (pode ter tokens) para mensagens de erro."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _decode(content: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    try:
        return content.decode(match.group(1) if match else "utf-8")
    except (LookupError, UnicodeDecodeError):
        return content.decode("utf-8", errors="replace")


# Notion -------------------------------------------------------------------------------------------------------------

_NOTION_HOSTS = ("notion.so", "notion.com", "notion.site")
# 32 dígitos hexadecimais (ou o UUID com hífens) que não estejam colados a outro dígito hexadecimal.
_NOTION_ID = re.compile(
    r"(?<![0-9a-f])([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?![0-9a-f])",
    re.IGNORECASE,
)
NOTION_HELP = (
    "Para ler páginas do Notion: crie uma integração interna em https://www.notion.so/profile/integrations, "
    "compartilhe a página com ela (menu ••• > Conexões) e defina a variável NOTION_TOKEN com o token da integração."
)


def is_notion(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in _NOTION_HOSTS)


def notion_id(url: str) -> str:
    """Identificador da página ou base de dados a partir da URL ("...Titulo-1f2e3d..." ou "?p=...")."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query)
    candidates = [*query.get("p", []), parts.path]
    for candidate in candidates:
        found = _NOTION_ID.findall(candidate)
        if found:
            raw = found[-1].replace("-", "").lower()
            return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    raise SourceError(f"Não encontrei o identificador da página na URL do Notion: {_safe_url(url)}")


def _rich(items) -> str:
    return "".join(item.get("plain_text", "") for item in items or [])


class NotionReader:
    """Lê páginas (blocos em Markdown) e bases de dados (tabela) pela API oficial do Notion."""

    def __init__(self, token: str, *, max_blocks: int = 3000, max_depth: int = 6, max_rows: int = 2000):
        self.token = token
        self.max_blocks = max_blocks
        self.max_depth = max_depth
        self.max_rows = max_rows
        self._blocks = 0
        self.known: dict[str, str] = {}

    def _person(self, user: dict | None) -> str:
        """Nome de um usuário do Notion, guardado como dado pessoal (e o e-mail, se a API mandar)."""
        user = user or {}
        name = (user.get("name") or "").strip()
        if name:
            self.known[name] = "PESSOA"
        email = ((user.get("person") or {}).get("email") or "").strip()
        if email:
            self.known[email] = "EMAIL"
        return name

    def _rich(self, items) -> str:
        """Texto rico do Notion; menções a pessoas (@nome) entram como dado pessoal."""
        for item in items or []:
            mention = item.get("mention") or {}
            if item.get("type") == "mention" and mention.get("type") == "user":
                name = self._person(mention.get("user"))
                if not name and item.get("plain_text", "").lstrip("@").strip():
                    self.known[item["plain_text"].lstrip("@").strip()] = "PESSOA"
        return _rich(items)

    def _call(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        content, _ = http(f"https://api.notion.com/v1/{path}", method=method, body=body, headers={
            "Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION,
        })
        return json.loads(content)

    def read(self, url: str) -> Document:
        identifier = notion_id(url)
        try:
            page = self._call(f"pages/{identifier}")
        except SourceError as exc:
            # O identificador pode ser de uma base de dados; se também falhar, vale o erro da página.
            try:
                return self.read_database(url, identifier)
            except SourceError:
                raise SourceError(f"{exc}. {NOTION_HELP}") from exc
        title = next((self._rich(p.get("title")) for p in page.get("properties", {}).values()
                      if p.get("type") == "title"), "")
        lines = [f"# {title}"] if title else []
        properties = self._properties(page.get("properties", {}))
        if properties:
            lines.append("\n".join(f"- **{name}:** {value}" for name, value in properties if value))
        lines.extend(self._children(identifier, 0))
        return Document(url, title, "\n\n".join(line for line in lines if line), "notion", dict(self.known))

    def read_database(self, url: str, identifier: str) -> Document:
        database = self._call(f"databases/{identifier}")
        title = self._rich(database.get("title"))
        rows, cursor = [], None
        while len(rows) < self.max_rows:
            body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            result = self._call(f"databases/{identifier}/query", "POST", body)
            rows.extend(result.get("results", []))
            cursor = result.get("next_cursor")
            if not result.get("has_more") or not cursor:
                break
        columns = list(database.get("properties", {}))
        table = [columns] + [
            [dict(self._properties(row.get("properties", {}), include_title=True)).get(c, "") for c in columns]
            for row in rows
        ]
        from veu.documents import _table_markdown

        return Document(url, title, f"# {title}\n\n{_table_markdown(table)}", "notion", dict(self.known))

    def _properties(self, properties: dict, include_title: bool = False) -> list[tuple[str, str]]:
        """Propriedades como texto. O título fica de fora na página (já vira o # título), mas não nas linhas de bases."""
        output = []
        for name, prop in properties.items():
            kind = prop.get("type")
            value = prop.get(kind)
            if kind == "title" and not include_title:
                continue
            if kind in ("title", "rich_text"):
                text = self._rich(value)
            elif kind in ("select", "status"):
                text = (value or {}).get("name", "")
            elif kind == "multi_select":
                text = ", ".join(item.get("name", "") for item in value or [])
            elif kind == "people":
                text = ", ".join(self._person(item) for item in value or [])
            elif kind == "date":
                text = (value or {}).get("start", "") or ""
            elif kind == "checkbox":
                text = "sim" if value else "não"
            elif kind == "formula":
                text = str((value or {}).get((value or {}).get("type", ""), "") or "")
            elif kind in ("number", "email", "phone_number", "url", "created_time", "last_edited_time"):
                text = "" if value is None else str(value)
            elif kind in ("created_by", "last_edited_by"):
                text = self._person(value)
            else:
                text = ""
            output.append((name, text))
        return output

    def _children(self, block_id: str, depth: int) -> list[str]:
        lines, cursor = [], None
        while self._blocks < self.max_blocks:
            query = f"?page_size=100{f'&start_cursor={cursor}' if cursor else ''}"
            result = self._call(f"blocks/{block_id}/children{query}")
            numbered = 0
            for block in result.get("results", []):
                self._blocks += 1
                kind = block.get("type", "")
                numbered = numbered + 1 if kind == "numbered_list_item" else 0
                line = self._block(block, numbered)
                indent = "  " * depth
                if line:
                    lines.append("\n".join(indent + part for part in line.split("\n")))
                if block.get("has_children") and depth < self.max_depth and kind not in ("child_page", "child_database"):
                    lines.extend(self._children(block["id"], depth + 1))
            cursor = result.get("next_cursor")
            if not result.get("has_more") or not cursor:
                break
        return lines

    def _block(self, block: dict, numbered: int) -> str:
        kind = block.get("type", "")
        data = block.get(kind, {}) or {}
        text = self._rich(data.get("rich_text"))
        prefix = {
            "heading_1": "# ", "heading_2": "## ", "heading_3": "### ", "bulleted_list_item": "- ", "quote": "> ",
            "toggle": "- ",
        }
        if kind in prefix:
            return prefix[kind] + text
        if kind == "numbered_list_item":
            return f"{numbered}. {text}"
        if kind == "to_do":
            return f"- [{'x' if data.get('checked') else ' '}] {text}"
        if kind == "callout":
            icon = (data.get("icon") or {}).get("emoji", "")
            return f"> {icon} {text}".replace(">  ", "> ")
        if kind == "code":
            return f"```{data.get('language', '')}\n{text}\n```"
        if kind == "divider":
            return "---"
        if kind == "child_page":
            return f"## {data.get('title', '')} (subpágina)"
        if kind == "child_database":
            return f"## {data.get('title', '')} (base de dados)"
        if kind == "table_row":
            return "| " + " | ".join(self._rich(cell) for cell in data.get("cells", [])) + " |"
        if kind == "equation":
            return f"$${data.get('expression', '')}$$"
        if kind in ("bookmark", "link_preview", "embed"):
            return data.get("url", "")
        if kind in ("image", "file", "pdf", "video", "audio"):
            caption = self._rich(data.get("caption"))
            return f"[{kind}{': ' + caption if caption else ''}]"
        return text


# Google -------------------------------------------------------------------------------------------------------------

_GOOGLE = re.compile(r"https://docs\.google\.com/(document|spreadsheets|presentation)/d/([A-Za-z0-9_-]{20,})")
GOOGLE_HELP = (
    "O documento não é público. Compartilhe como \"Qualquer pessoa com o link\" ou defina GOOGLE_ACCESS_TOKEN "
    "com um token OAuth com acesso de leitura ao Drive."
)


def is_google(url: str) -> bool:
    return _GOOGLE.match(url) is not None


def read_google(url: str, token: str | None = None) -> Document:
    match = _GOOGLE.match(url)
    if not match:
        raise SourceError(f"URL do Google não reconhecida: {_safe_url(url)}")
    kind, identifier = match.groups()
    gid = re.search(r"[#&?]gid=(\d+)", url)
    if token:
        mime = {"document": "text/plain", "spreadsheets": "text/csv", "presentation": "text/plain"}[kind]
        export = f"https://www.googleapis.com/drive/v3/files/{identifier}/export?mimeType={urllib.parse.quote(mime, safe='')}"
        content, content_type = http(export, headers={"Authorization": f"Bearer {token}"})
    else:
        export = {
            "document": f"https://docs.google.com/document/d/{identifier}/export?format=txt",
            "spreadsheets": f"https://docs.google.com/spreadsheets/d/{identifier}/export?format=csv"
                            + (f"&gid={gid.group(1)}" if gid else ""),
            "presentation": f"https://docs.google.com/presentation/d/{identifier}/export/txt",
        }[kind]
        content, content_type = http(export)
        if "text/html" in content_type:
            raise SourceError(GOOGLE_HELP)
    names = {"document": "google-docs", "spreadsheets": "google-sheets", "presentation": "google-slides"}
    text = _decode(content, content_type).lstrip("﻿")
    if kind == "spreadsheets":
        import csv
        import io

        from veu.documents import _table_markdown

        text = _table_markdown(list(csv.reader(io.StringIO(text))))
    return Document(url, "", text, names[kind])


# Páginas web --------------------------------------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCKS = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "header",
              "footer", "main", "aside", "nav", "table", "ul", "ol", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self._skip:
            self.parts.append("#" * int(tag[1]) + " ")
        if tag == "li" and not self._skip:
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in joined.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.title.strip(), parser.text()


def read_url(url: str) -> Document:
    content, content_type = http(url)
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    kind = DOCUMENT_EXTENSIONS.get(suffix)
    mime_kinds = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    }
    kind = next((value for mime, value in mime_kinds.items() if mime in content_type), kind)
    if kind:
        return Document(url, Path(urllib.parse.urlsplit(url).path).name, read_document(content, kind), kind)
    text = _decode(content, content_type)
    if "html" in content_type or text.lstrip()[:15].lower().startswith(("<!doctype html", "<html")):
        title, body = html_to_text(text)
        return Document(url, title, body, "web")
    return Document(url, "", text, "web")


# Ponto de entrada ---------------------------------------------------------------------------------------------------

def read_source(source: str, *, notion_token: str | None = None, google_token: str | None = None) -> Document:
    """Lê uma URL (Notion, Google, web) ou um arquivo local e devolve o texto, ainda sem anonimizar."""
    source = source.strip()
    if re.match(r"https?://", source, re.IGNORECASE):
        if is_notion(source):
            token = notion_token or os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
            if not token:
                raise SourceError(NOTION_HELP)
            return NotionReader(token).read(source)
        if is_google(source):
            return read_google(source, google_token or os.environ.get("GOOGLE_ACCESS_TOKEN"))
        return read_url(source)
    path = Path(source).expanduser()
    if not path.is_file():
        raise SourceError(f"Arquivo não encontrado: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise SourceError("Arquivo maior que 20 MB.")
    kind = DOCUMENT_EXTENSIONS.get(path.suffix.lower())
    if kind:
        return Document(str(path), path.name, read_document(path, kind), kind)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        title, text = html_to_text(text)
        return Document(str(path), title or path.name, text, "web")
    return Document(str(path), path.name, text, "texto")


# Expansão de links no proxy -----------------------------------------------------------------------------------------

_URL = re.compile(r"https?://[^\s<>\"'()\[\]]+")


class LinkExpander:
    """Troca links do Notion e do Google (e de outros domínios permitidos) pelo conteúdo, para o modelo ler.

    Só busca domínios da lista (proteção contra SSRF), guarda o conteúdo por alguns minutos e limita o tamanho.
    """

    def __init__(self, domains: tuple[str, ...] = ("notion.so", "notion.com", "notion.site", "docs.google.com"), *,
                 max_chars: int = 100_000, ttl: float = 600.0, reader=read_source):
        self.domains = tuple(domain.lower().lstrip(".") for domain in domains)
        self.max_chars = max_chars
        self.ttl = ttl
        self.reader = reader
        self._cache: dict[str, tuple[float, str, dict[str, str]]] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and any(host == d or host.endswith("." + d) for d in self.domains)

    def _content(self, url: str) -> tuple[str, dict[str, str]]:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(url)
            if cached and now - cached[0] < self.ttl:
                return cached[1], cached[2]
        known: dict[str, str] = {}
        try:
            document = self.reader(url)
            text = document.text[: self.max_chars]
            known = dict(getattr(document, "known", {}) or {})
            content = f"\n\n[Conteúdo de {url}]\n{text}\n[Fim do conteúdo]"
        except (SourceError, ImportError, ValueError) as exc:
            content = f"\n\n[O Véu não conseguiu ler {_safe_url(url)}: {exc}]"
        with self._lock:
            self._cache[url] = (now, content, known)
        return content, known

    def expand_with_known(self, text: str) -> tuple[str, dict[str, str]]:
        """Texto com o conteúdo dos links permitidos e os dados pessoais que a fonte informou (para esconder)."""
        urls = [match.group(0).rstrip(".,;:!?") for match in _URL.finditer(text)]
        known: dict[str, str] = {}
        additions = []
        for url in dict.fromkeys(urls):
            if self.allowed(url):
                content, found = self._content(url)
                additions.append(content)
                known.update(found)
        return (text + "".join(additions) if additions else text), known

    def expand(self, text: str) -> str:
        return self.expand_with_known(text)[0]
