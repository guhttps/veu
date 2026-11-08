"""Servidor MCP do Véu (pip install "veu[mcp]"), para Claude Code, Claude Desktop, Cursor e outros agentes.

    veu mcp                         # servidor stdio
    claude mcp add veu -- veu mcp   # registrar no Claude Code

As ferramentas de arquivo processam os dados na sua máquina e devolvem só contagens e valores
mascarados: o agente consegue auditar e anonimizar arquivos sem que os dados entrem na conversa.

A restauração que devolve os dados reais para a conversa (restaurar_texto) fica desligada por padrão: um
texto malicioso lido pelo agente poderia pedir que ele a chamasse. Para ligar: veu mcp --com-restauracao.
As restaurações para arquivo (restaurar_para_arquivo, restaurar_arquivo) gravam no disco e devolvem só o caminho.
"""

from __future__ import annotations

import functools
import json
from collections import Counter
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

# O pydantic (usado pelo MCP) exige o TypedDict do typing_extensions no Python < 3.12.
from typing_extensions import TypedDict

from veu import __version__
from veu.anonymizer import mask_value, normalize_operator
from veu.core import Veu
from veu.entities import LABELS
from veu.files import anonymize_file, detect_format
from veu.server.state import SessionStore
from veu.vault import Vault

MAX_FILE_BYTES = 20 * 1024 * 1024
INSTRUCTIONS = (
    "O Véu encontra e esconde dados pessoais e segredos (nomes, e-mails, telefones, endereços, CPF, CNPJ, cartões, "
    "chaves de API, senhas...). Para ler uma página do Notion, um Google Docs/Sheets, um link ou um documento (Word, "
    "Excel, PowerPoint, PDF), use ler_protegido: o conteúdo chega com os dados trocados por marcadores. Para arquivos, "
    "prefira verificar_arquivo e anonimizar_arquivo: eles processam os dados localmente e devolvem só contagens e "
    "valores mascarados, sem trazer os dados pessoais para a conversa."
)


class Ocorrencia(TypedDict):
    entidade: str
    linha: int
    coluna: int
    valor_mascarado: str
    pontuacao: float


class Verificacao(TypedDict):
    arquivo: str
    total: int
    por_entidade: dict[str, int]
    ocorrencias: list[Ocorrencia]


class ArquivoAnonimizado(TypedDict):
    destino: str
    formato: str
    escondidos: dict[str, int]
    cofre: str | None


class Deteccao(TypedDict):
    entidade: str
    inicio: int
    fim: int
    valor_mascarado: str
    pontuacao: float


class TextoAnonimizado(TypedDict):
    texto: str
    sessao: str
    escondidos: dict[str, int]


class ArquivoRestaurado(TypedDict):
    destino: str


class TextoRestaurado(TypedDict):
    destino: str
    restaurados: int


class FonteLida(TypedDict):
    fonte: str
    titulo: str
    tipo: str
    texto: str
    sessao: str
    escondidos: dict[str, int]


def _expected_errors(function):
    """Erros esperados (arquivo inexistente, sessão expirada...) chegam ao agente como mensagem, sem traceback."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _file(path: str) -> Path:
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"Arquivo não encontrado: {file}")
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Arquivo maior que 20 MB.")
    return file


# O modelo escolhe onde gravar e, em restaurar_para_arquivo, o que gravar; e ele pode ter sido manipulado por um
# texto que leu. Por isso, as ferramentas só criam documentos novos: nada de scripts (.bat, .ps1, .sh), de pastas ou
# arquivos ocultos (.ssh, .bashrc) nem de sobrescrever o que já existe.
SAFE_OUTPUTS = frozenset({".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".docx", ".xlsx", ".pptx",
                          ".pdf"})


def _output(path: str, extensions: frozenset[str] = SAFE_OUTPUTS) -> Path:
    target = Path(path).expanduser()
    if any(part.startswith(".") and part not in (".", "..") for part in target.parts):
        raise ValueError(f"O Véu não grava em pastas ou arquivos ocultos ({target}). Escolha outro lugar.")
    if target.suffix.lower() not in extensions:
        raise ValueError(f"O Véu só grava documentos ({', '.join(sorted(extensions))}). Escolha outro nome.")
    if target.exists():
        raise ValueError(f"O arquivo {target} já existe. Escolha outro nome.")
    return target


def _create(target: Path, write) -> None:
    """Cria o arquivo de forma exclusiva (se outro processo criar no meio do caminho, falha) e depois grava."""
    try:
        target.open("x").close()
    except FileExistsError as exc:
        raise ValueError(f"O arquivo {target} já existe. Escolha outro nome.") from exc
    try:
        write()
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _read(path: str) -> tuple[Path, str]:
    """Texto do arquivo; Word, Excel, PowerPoint e PDF são convertidos em texto."""
    from veu.documents import document_kind, read_document

    file = _file(path)
    kind = document_kind(file)
    if kind:
        try:
            return file, read_document(file, kind)
        except ImportError as exc:
            raise ValueError(str(exc)) from exc
    return file, file.read_text(encoding="utf-8-sig", errors="replace")


def build_server(veu: Veu | None = None, *, restore_text: bool = False) -> MCPServer:
    """restore_text: inclui restaurar_texto, que devolve os dados reais para a conversa."""
    instance = veu or Veu()
    sessions = SessionStore(instance.new_vault, ttl=3600)
    server = MCPServer(name="veu", title="Véu", instructions=INSTRUCTIONS, version=__version__,
                       website_url="https://github.com/guhttps/veu")

    @server.tool(description="Verifica um arquivo local e lista os dados pessoais encontrados, com os valores "
                             "mascarados (nunca o valor completo), linha e coluna.")
    @_expected_errors
    def verificar_arquivo(caminho: str) -> Verificacao:
        file, text = _read(caminho)
        lines = text.splitlines(keepends=True)
        starts, position = [], 0
        for line in lines:
            starts.append(position)
            position += len(line)
        found = []
        for entity in instance.analyze(text):
            line = max((i for i, start in enumerate(starts) if start <= entity.start), default=0)
            found.append({
                "entidade": entity.label,
                "linha": line + 1,
                "coluna": entity.start - (starts[line] if starts else 0) + 1,
                "valor_mascarado": mask_value(entity.label, entity.text),
                "pontuacao": round(entity.score, 2),
            })
        counts = Counter(item["entidade"] for item in found)
        return {"arquivo": str(file), "total": len(found), "por_entidade": dict(counts), "ocorrencias": found[:500]}

    @server.tool(description="Cria uma cópia anonimizada de um arquivo (texto, CSV, JSON, JSONL, Word, Excel ou "
                             "PowerPoint, no mesmo formato; PDF vira texto) sem trazer o conteúdo para a conversa. "
                             "Opcionalmente salva o cofre (que contém os dados reais) para restaurar depois.")
    @_expected_errors
    def anonimizar_arquivo(origem: str, destino: str, formato: str | None = None, campos: list[str] | None = None,
                           forcar: dict[str, str] | None = None, operador: str | None = None,
                           salvar_cofre: str | None = None) -> ArquivoAnonimizado:
        source = _file(origem)
        target = _output(destino)
        vault_file = _output(salvar_cofre, frozenset({".json"})) if salvar_cofre else None
        engine = instance.with_operator(normalize_operator(operador)) if operador else instance
        result: dict = {}

        def write() -> None:
            result["vault"], result["counts"] = anonymize_file(source, target, veu=engine, file_format=formato,
                                                               fields=campos, force=forcar)

        _create(target, write)
        vault, counts = result["vault"], result["counts"]
        if vault_file is not None:
            _create(vault_file, lambda: vault_file.write_text(json.dumps(vault.to_dict(), ensure_ascii=False),
                                                              encoding="utf-8"))
        return {"destino": str(target), "formato": detect_format(source, formato),
                "escondidos": dict(counts), "cofre": salvar_cofre}

    @server.tool(description="Lê uma página do Notion, um Google Docs/Sheets/Slides, uma página web ou um documento "
                             "local (Word, Excel, PowerPoint, PDF, texto) e devolve o conteúdo já protegido: dados "
                             "pessoais e segredos viram marcadores como [PESSOA_1]. Se o usuário pedir a resposta com "
                             "os dados reais, use a sessão devolvida com restaurar_para_arquivo.")
    @_expected_errors
    def ler_protegido(fonte: str, sessao: str | None = None) -> FonteLida:
        from veu.sources import SourceError, read_source

        try:
            document = read_source(fonte)
        except (SourceError, ImportError) as exc:
            raise ToolError(str(exc)) from exc
        if sessao:
            vault = sessions.get(sessao, create=False)
            if vault is None:
                raise ValueError("Sessão não encontrada ou expirada.")
        else:
            sessao = SessionStore.new_id()
            vault = sessions.get(sessao)
        from veu.sources import protect_document

        title, text, counts = protect_document(document, instance.anonymizer, vault)
        return {"fonte": fonte, "titulo": title, "tipo": document.kind, "texto": text, "sessao": sessao,
                "escondidos": dict(counts)}

    @server.tool(description="Lista os dados pessoais de um texto (tipo, posição e valor mascarado).")
    def detectar(texto: str) -> list[Deteccao]:
        return [{"entidade": e.label, "inicio": e.start, "fim": e.end, "valor_mascarado": mask_value(e.label, e.text),
                 "pontuacao": round(e.score, 2)} for e in instance.analyze(texto)]

    @server.tool(description="Troca os dados pessoais de um texto por marcadores como [CPF_1]. Devolve o texto e "
                             "uma sessão para restaurar a resposta depois.")
    @_expected_errors
    def anonimizar_texto(texto: str, sessao: str | None = None, operador: str | None = None) -> TextoAnonimizado:
        if sessao:
            vault = sessions.get(sessao, create=False)
            if vault is None:
                raise ValueError("Sessão não encontrada ou expirada.")
        else:
            sessao = SessionStore.new_id()
            vault = sessions.get(sessao)
        engine = instance.with_operator(normalize_operator(operador)) if operador else instance
        result = engine.anonymize(texto, vault)
        return {"texto": result.text, "sessao": sessao, "escondidos": dict(result.counts())}

    def _session_vault(sessao: str) -> Vault:
        vault = sessions.get(sessao, create=False)
        if vault is None:
            raise ValueError("Sessão não encontrada ou expirada.")
        return vault

    @server.tool(description="Grava num arquivo local o texto com os dados reais no lugar dos marcadores de uma "
                             "sessão (por exemplo, a resposta final para o usuário). Devolve só o caminho: os dados "
                             "reais não voltam para a conversa. Links e URLs continuam com os marcadores. Não sobrescreve "
                             "arquivos existentes.")
    @_expected_errors
    def restaurar_para_arquivo(texto: str, sessao: str, destino: str) -> TextoRestaurado:
        vault = _session_vault(sessao)
        target = _output(destino)  # o texto vem do modelo: só documentos novos, nunca scripts nem sobrescrever
        _create(target, lambda: target.write_text(vault.restore(texto), encoding="utf-8"))
        return {"destino": str(target), "restaurados": len(vault.restore_spans(texto))}

    if restore_text:
        @server.tool(description="Devolve os dados reais no lugar dos marcadores de uma sessão. Atenção: o "
                                 "resultado contém os dados pessoais. Use só quando o usuário pedir.")
        @_expected_errors
        def restaurar_texto(texto: str, sessao: str) -> str:
            return _session_vault(sessao).restore(texto)

    @server.tool(description="Restaura um arquivo anonimizado usando um cofre salvo por anonimizar_arquivo.")
    @_expected_errors
    def restaurar_arquivo(origem: str, destino: str, cofre: str, formato: str | None = None) -> ArquivoRestaurado:
        from veu.files import restore_file

        vault = Vault.from_dict(json.loads(Path(cofre).read_text(encoding="utf-8")))
        target = _output(destino)
        _create(target, lambda: restore_file(_file(origem), target, vault, file_format=formato))
        return {"destino": str(target)}

    @server.tool(description="Lista os tipos de dados pessoais que o Véu detecta.")
    def listar_entidades() -> dict[str, str]:
        return dict(LABELS)

    return server


def main() -> None:
    build_server().run("stdio")
