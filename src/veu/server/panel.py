"""Painel do Véu (veu painel): configuração por caixinhas, conexão com aplicativos e reinício do servidor.

Tudo que o painel salva vai para um veu.toml na pasta de configuração do usuário. Quem preferir pode editar o
arquivo à mão: o painel só muda as opções que ele mostra e mantém o resto.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from veu.config import Config

# Grupos de tipos, com nomes que qualquer pessoa entende.
CATEGORIES: dict[str, dict[str, Any]] = {
    "pessoas": {
        "titulo": "Nomes e contatos",
        "exemplo": "nomes, telefones, e-mails, endereços, CEP, datas de nascimento",
        "tipos": ["PESSOA", "TELEFONE", "EMAIL", "ENDERECO", "CEP", "DATA_NASCIMENTO"],
    },
    "documentos": {
        "titulo": "Documentos",
        "exemplo": "CPF, CNPJ, RG, CNH, título de eleitor, PIS, cartão do SUS, passaporte, processos",
        "tipos": ["CPF", "CNPJ", "RG", "CNH", "TITULO_ELEITOR", "PIS", "CNS", "PASSAPORTE", "PROCESSO"],
    },
    "estrangeiros": {
        "titulo": "Documentos de outros países",
        "exemplo": "Portugal (NIF, Cartão de Cidadão), Argentina (CUIT, DNI), México (CURP, RFC), Chile (RUT) e mais",
        "tipos": ["NIF_PT", "CC_PT", "NISS_PT", "CUIT", "DNI", "CURP", "RFC", "RUT", "CEDULA", "NIT", "RUC", "RIF"],
    },
    "financeiro": {
        "titulo": "Dados financeiros",
        "exemplo": "cartões, contas bancárias, chave Pix, IBAN",
        "tipos": ["CARTAO_CREDITO", "CONTA_BANCARIA", "CHAVE_PIX", "IBAN"],
    },
    "segredos": {
        "titulo": "Senhas e chaves de acesso",
        "exemplo": "senhas, chaves de API, tokens, chaves privadas",
        "tipos": ["CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO"],
    },
    "outros": {
        "titulo": "Veículos e internet",
        "exemplo": "placas, RENAVAM, endereços IP",
        "tipos": ["PLACA", "RENAVAM", "IP"],
    },
}
BLOCK_OPTIONS: dict[str, dict[str, Any]] = {
    "chaves_privadas": {"titulo": "Chaves privadas", "tipos": ["CHAVE_PRIVADA"]},
    "senhas": {"titulo": "Senhas e chaves de API", "tipos": ["SENHA", "CHAVE_API", "TOKEN", "URL_CONEXAO", "SEGREDO"]},
    "cartoes": {"titulo": "Números de cartão", "tipos": ["CARTAO_CREDITO"]},
}
OPERATORS = {
    "token": "Marcadores, como [CPF_1] (recomendado)",
    "sintetico": "Dados falsos realistas, como outro CPF válido",
    "mascara": "Máscara, como ***.982.247-** (não volta)",
}


def user_config_path() -> Path:
    """Onde o painel guarda o veu.toml: %APPDATA%\\veu no Windows, ~/Library/Application Support no macOS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "veu" / "veu.toml"


# Configurações simples <-> veu.toml ------------------------------------------------------------------------------

def settings_from_config(config: Config) -> dict:
    chosen = set(config.labels)
    categories = [key for key, group in CATEGORIES.items() if not chosen or chosen & set(group["tipos"])]
    blocked = set(config.block)
    return {
        "categorias": categories,
        "ignorar": list(config.allowlist),
        "bloquear": [key for key, option in BLOCK_OPTIONS.items() if blocked & set(option["tipos"])],
        "operador": config.operator if config.operator in OPERATORS else "token",
        "desvio": config.route_to == "ollama",
        "modelo_local": config.route_model or "",
    }


def validate_settings(settings: dict) -> dict:
    categories = [key for key in settings.get("categorias", []) if key in CATEGORIES]
    if not categories:
        raise ValueError("Escolha pelo menos um tipo de dado para proteger.")
    block = [key for key in settings.get("bloquear", []) if key in BLOCK_OPTIONS]
    operator = settings.get("operador", "token")
    if operator not in OPERATORS:
        raise ValueError("Forma de esconder desconhecida.")
    ignore = [line.strip() for line in settings.get("ignorar", []) if isinstance(line, str) and line.strip()][:500]
    route = bool(settings.get("desvio"))
    model = str(settings.get("modelo_local") or "").strip()[:100]
    if route and not model:
        raise ValueError("Informe o modelo local do Ollama, por exemplo llama3.1.")
    return {"categorias": categories, "bloquear": block, "operador": operator, "ignorar": ignore, "desvio": route,
            "modelo_local": model}


def apply_settings(path: Path, settings: dict) -> None:
    """Grava as escolhas do painel no veu.toml, mantendo as outras opções que já estavam lá."""
    settings = validate_settings(settings)
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    detection = data.setdefault("deteccao", {})
    if len(settings["categorias"]) == len(CATEGORIES):
        detection.pop("entidades", None)  # todos os tipos
    else:
        detection["entidades"] = [label for key in settings["categorias"] for label in CATEGORIES[key]["tipos"]]
    if settings["ignorar"]:
        detection["ignorar"] = settings["ignorar"]
    else:
        detection.pop("ignorar", None)
    data.setdefault("anonimizacao", {})["operador"] = settings["operador"]
    policy = data.setdefault("politica", {})
    policy["bloquear"] = [label for key in settings["bloquear"] for label in BLOCK_OPTIONS[key]["tipos"]]
    if settings["desvio"]:  # textos com dados pessoais vão inteiros para o modelo local, sem sair do computador
        policy["desviar_para"] = "ollama"
        policy["modelo_desvio"] = settings["modelo_local"]
    elif policy.get("desviar_para") == "ollama":
        policy.pop("desviar_para", None)
        policy.pop("modelo_desvio", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Configuração do Véu. O painel (veu painel) mantém este arquivo; também pode ser editado à mão.\n\n"
    path.write_text(header + dump_toml(data), encoding="utf-8")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"Valor sem representação em TOML: {value!r}")


def _toml_key(key: str) -> str:
    return key if key.replace("_", "").replace("-", "").isalnum() and key.isascii() else json.dumps(key)


def dump_toml(data: dict, prefix: str = "") -> str:
    """TOML simples (o Python só traz o leitor): tabelas, listas de tabelas e valores comuns."""
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)
               and not (isinstance(v, list) and v and all(isinstance(item, dict) for item in v))}
    for key, value in scalars.items():
        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    blocks: list[str] = ["\n".join(lines)] if lines else []
    for key, value in data.items():
        name = f"{prefix}.{_toml_key(key)}" if prefix else _toml_key(key)
        if isinstance(value, dict):
            inner = dump_toml(value, name)
            blocks.append(f"[{name}]\n{inner}".rstrip())
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for item in value:
                blocks.append(f"[[{name}]]\n{dump_toml(item, name)}".rstrip())
    return "\n\n".join(block for block in blocks if block.strip()) + "\n"


# Aplicativos que usam o Véu pelo MCP ------------------------------------------------------------------------------

def mcp_apps() -> dict[str, dict[str, Any]]:
    """Arquivos de configuração MCP do Claude Desktop e do Cursor neste computador."""
    home = Path.home()
    if sys.platform == "win32":
        claude = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "Claude"
    elif sys.platform == "darwin":
        claude = home / "Library" / "Application Support" / "Claude"
    else:
        claude = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude"
    return {
        "claude": {"titulo": "Claude Desktop", "arquivo": claude / "claude_desktop_config.json", "pasta": claude},
        "cursor": {"titulo": "Cursor", "arquivo": home / ".cursor" / "mcp.json", "pasta": home / ".cursor"},
    }


def mcp_entry() -> dict:
    from veu.atalhos import veu_command

    command = veu_command()
    return {"command": command[0], "args": [*command[1:], "mcp"]}


def mcp_status(app: str) -> dict:
    info = mcp_apps()[app]
    installed = info["pasta"].is_dir()
    connected = False
    if info["arquivo"].is_file():
        try:
            connected = "veu" in json.loads(info["arquivo"].read_text(encoding="utf-8") or "{}").get("mcpServers", {})
        except (ValueError, AttributeError):
            connected = False
    return {"titulo": info["titulo"], "instalado": installed, "conectado": connected}


def connect_mcp(app: str, enable: bool = True) -> dict:
    """Acrescenta (ou tira) o servidor MCP do Véu na configuração do aplicativo, guardando uma cópia do original."""
    import importlib.util

    if enable and importlib.util.find_spec("mcp") is None:
        raise ValueError('Falta o suporte a MCP. Reinstale com o instalador do Véu ou: pip install "veu[mcp]"')
    info = mcp_apps()[app]
    file: Path = info["arquivo"]
    data: dict = {}
    if file.is_file():
        text = file.read_text(encoding="utf-8")
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError as exc:
            raise ValueError(f"Não consegui ler {file}: o arquivo não é um JSON válido.") from exc
        shutil.copyfile(file, file.with_suffix(file.suffix + ".antes-do-veu"))
    servers = data.setdefault("mcpServers", {})
    if enable:
        servers["veu"] = mcp_entry()
    else:
        servers.pop("veu", None)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return mcp_status(app)


# Controle do servidor do painel -----------------------------------------------------------------------------------

@dataclass
class PanelController:
    """Liga o painel ao processo: salvar as configurações reinicia o servidor com o veu.toml novo."""

    config_path: Path
    restart: bool = False
    server: Any = None
    extras: dict = field(default_factory=dict)

    def stop(self, restart: bool = False) -> None:
        self.restart = restart
        if self.server is not None:
            self.server.should_exit = True
