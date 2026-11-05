"""Servidor MCP do Véu (pip install "veu[mcp]"), para Claude Code, Claude Desktop, Cursor e outros agentes.

    veu mcp                         # servidor stdio
    claude mcp add veu -- veu mcp   # registrar no Claude Code

As ferramentas de arquivo processam os dados na sua máquina e devolvem só contagens e valores
mascarados: o agente consegue auditar e anonimizar arquivos sem que os dados entrem na conversa.
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
    "O Véu encontra e esconde dados pessoais brasileiros (CPF, CNPJ, nomes, telefones, e-mails, endereços...). "
    "Para arquivos, prefira verificar_arquivo e anonimizar_arquivo: eles processam os dados localmente e devolvem "
    "só contagens e valores mascarados, sem trazer os dados pessoais para a conversa."
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


def _expected_errors(function):
    """Erros esperados (arquivo inexistente, sessão expirada...) chegam ao agente como mensagem, sem traceback."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _read(path: str) -> tuple[Path, str]:
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"Arquivo não encontrado: {file}")
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Arquivo maior que 20 MB.")
    return file, file.read_text(encoding="utf-8-sig", errors="replace")


def build_server(veu: Veu | None = None) -> MCPServer:
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

    @server.tool(description="Cria uma cópia anonimizada de um arquivo (texto, CSV, JSON ou JSONL) sem trazer o "
                             "conteúdo para a conversa. Opcionalmente salva o cofre (que contém os dados reais) "
                             "para restaurar depois.")
    @_expected_errors
    def anonimizar_arquivo(origem: str, destino: str, formato: str | None = None, campos: list[str] | None = None,
                           forcar: dict[str, str] | None = None, operador: str | None = None,
                           salvar_cofre: str | None = None) -> ArquivoAnonimizado:
        source, _ = _read(origem)
        engine = instance.with_operator(normalize_operator(operador)) if operador else instance
        vault, counts = anonymize_file(source, destino, veu=engine, file_format=formato, fields=campos, force=forcar)
        if salvar_cofre:
            Path(salvar_cofre).write_text(json.dumps(vault.to_dict(), ensure_ascii=False), encoding="utf-8")
        return {"destino": str(Path(destino)), "formato": detect_format(source, formato),
                "escondidos": dict(counts), "cofre": salvar_cofre}

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

    @server.tool(description="Devolve os dados reais no lugar dos marcadores de uma sessão. Atenção: o resultado "
                             "contém os dados pessoais.")
    @_expected_errors
    def restaurar_texto(texto: str, sessao: str) -> str:
        vault = sessions.get(sessao, create=False)
        if vault is None:
            raise ValueError("Sessão não encontrada ou expirada.")
        return vault.restore(texto)

    @server.tool(description="Restaura um arquivo anonimizado usando um cofre salvo por anonimizar_arquivo.")
    @_expected_errors
    def restaurar_arquivo(origem: str, destino: str, cofre: str, formato: str | None = None) -> ArquivoRestaurado:
        from veu.files import restore_file

        vault = Vault.from_dict(json.loads(Path(cofre).read_text(encoding="utf-8")))
        restore_file(origem, destino, vault, file_format=formato)
        return {"destino": str(Path(destino))}

    @server.tool(description="Lista os tipos de dados pessoais que o Véu detecta.")
    def listar_entidades() -> dict[str, str]:
        return dict(LABELS)

    return server


def main() -> None:
    build_server().run("stdio")
