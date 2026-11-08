"""Configuração: arquivo veu.toml e variáveis de ambiente VEU_*."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from veu.anonymizer import normalize_operator
from veu.entities import LABELS


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    kind: str  # "openai", "anthropic", "gemini" ou "ollama"
    url: str
    key_env: str | None = None
    # Regras próprias do provedor (None = usar as globais).
    anonymize: bool = True
    operator: str | None = None
    block: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TeamConfig:
    """Equipe com token próprio ([equipes.NOME]): a auditoria e as métricas mostram quem chamou."""

    name: str
    token: str | None
    block: tuple[str, ...] | None = None
    operator: str | None = None


# Provedores conhecidos. "openai" inclui qualquer API compatível com OpenAI Chat Completions.
BUILTIN_PROVIDERS: dict[str, ProviderConfig] = {
    provider.name: provider
    for provider in (
        ProviderConfig("openai", "openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
        ProviderConfig("anthropic", "anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY"),
        ProviderConfig("gemini", "gemini", "https://generativelanguage.googleapis.com", "GEMINI_API_KEY"),
        ProviderConfig("gemini-openai", "openai", "https://generativelanguage.googleapis.com/v1beta/openai",
                       "GEMINI_API_KEY"),
        ProviderConfig("groq", "openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
        ProviderConfig("openrouter", "openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
        ProviderConfig("deepseek", "openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
        ProviderConfig("mistral", "openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
        ProviderConfig("together", "openai", "https://api.together.xyz/v1", "TOGETHER_API_KEY"),
        ProviderConfig("maritaca", "openai", "https://chat.maritaca.ai/api", "MARITACA_API_KEY"),
        ProviderConfig("xai", "openai", "https://api.x.ai/v1", "XAI_API_KEY"),
        ProviderConfig("perplexity", "openai", "https://api.perplexity.ai", "PERPLEXITY_API_KEY"),
        ProviderConfig("fireworks", "openai", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
        ProviderConfig("cerebras", "openai", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
        ProviderConfig("huggingface", "openai", "https://router.huggingface.co/v1", "HF_TOKEN"),
        ProviderConfig("cohere", "openai", "https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
        ProviderConfig("nvidia", "openai", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
        ProviderConfig("sambanova", "openai", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
        # Locais. O Ollama atende tanto a API compatível com OpenAI (/v1) quanto a nativa (/api/chat).
        ProviderConfig("ollama", "ollama", "http://localhost:11434"),
        ProviderConfig("lmstudio", "openai", "http://localhost:1234/v1"),
        ProviderConfig("vllm", "openai", "http://localhost:8000/v1"),
        ProviderConfig("llamacpp", "openai", "http://localhost:8080/v1"),
    )
}
PROVIDER_KINDS = ("openai", "anthropic", "gemini", "ollama")
MIN_SECRET_LENGTH = 32
_SECRETS = ("CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO")

# Perfis: pontos de partida para setores com regras próprias. Cada um só ajusta opções do Véu; nenhum garante
# conformidade (veja docs/conformidade.md). Opções escritas no veu.toml valem mais que as do perfil.
PROFILES: dict[str, dict] = {
    "pseudonimizacao": {
        "descricao": "Padrão: marcadores reversíveis ([CPF_1]); a resposta volta com os dados reais. É pseudonimização "
                     "(LGPD, art. 13, § 4º): o dado continua pessoal.",
    },
    "anonimizacao": {
        "descricao": "Irreversível: os dados viram o tipo ([CPF]) e nenhum cofre guarda os valores. Pode sustentar o "
                     "art. 12 da LGPD, sujeito à avaliação do risco de reidentificação pelo contexto.",
        "operator": "remover", "block": _SECRETS,
    },
    "judiciario": {
        "descricao": "CNJ, Resolução 615/2025: dados sigilosos só vão a IA externa anonimizados. Irreversível, segredos "
                     "bloqueados; use com a auditoria ligada (registro de uso).",
        "operator": "remover", "block": _SECRETS,
    },
    "juridico": {
        "descricao": "Escritórios (OAB, Recomendação 001/2024): sigilo profissional. Reversível, para a peça voltar com "
                     "os nomes das partes; segredos bloqueados.",
        "block": _SECRETS,
    },
    "saude": {
        "descricao": "Saúde (CFM, Resolução 2.454/2026: só o estritamente necessário). Reversível; segredos bloqueados; "
                     "com desviar_para configurado, textos com Cartão do SUS vão para o modelo interno.",
        "block": _SECRETS, "route_labels": ("CNS",),
    },
    "financeiro": {
        "descricao": "Bancos e fintechs: cartões, contas e IBAN saem removidos (irreversível); o resto, reversível; "
                     "segredos bloqueados.",
        "block": _SECRETS, "operators": {"CARTAO_CREDITO": "remover", "CONTA_BANCARIA": "remover", "IBAN": "remover"},
    },
    "setor-publico": {
        "descricao": "Órgãos públicos (guia de IA generativa do TCU: só dados públicos em plataformas externas). "
                     "Qualquer dado pessoal ou segredo faz a requisição ser recusada.",
        "block": tuple(LABELS),
    },
}


def profile_options(name: str) -> dict:
    """Opções de Config de um perfil (sem a descrição)."""
    if name not in PROFILES:
        raise ConfigError(f"Perfil desconhecido: {name}. Use um de {', '.join(PROFILES)}.")
    return {key: value for key, value in PROFILES[name].items() if key != "descricao"}
DETECTORS = ("padroes", "nomes", "enderecos", "segredos", "spacy", "llm", "ml")
PLUGIN_GROUP = "veu.detectores"


def plugin_detectors() -> set[str]:
    """Detectores instalados por outros pacotes (entry points do grupo veu.detectores)."""
    from importlib.metadata import entry_points

    return {entry.name for entry in entry_points(group=PLUGIN_GROUP)}


@dataclass(frozen=True)
class Config:
    # Detecção
    threshold: float = 0.5
    labels: tuple[str, ...] = ()
    allowlist: tuple[str, ...] = ()
    # Expressões regulares: valores que casarem nunca são escondidos (ex.: "@minhaempresa\\.com\\.br$").
    allow_patterns: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ("padroes", "nomes", "enderecos", "segredos")
    # Modelo do detector "ml" (transformers, pip install "veu[ml]").
    ml_model: str = "linc42/pii-ner-pt-br-bertimbau"
    # Itens no cache de detecção (0 desliga): agentes reenviam a conversa inteira a cada turno.
    detection_cache: int = 2048
    custom_patterns: tuple[dict, ...] = ()
    spacy_model: str = "pt_core_news_lg"
    llm_url: str | None = None
    llm_model: str | None = None
    llm_key_env: str | None = None
    # Anonimização
    operator: str = "token"
    operators: dict[str, str] = field(default_factory=dict)
    instruct_model: bool = True
    link_names: bool = True
    secret: str | None = None
    # Restauração: onde os dados reais podem voltar (veja veu.vault.RestorePolicy).
    restore_links: bool = False
    restore_link_hosts: tuple[str, ...] = ()
    restore_tools: bool = True
    restore_secrets_in_tools: bool = False
    restore_max_per_response: int = 0
    # Política
    profile: str = "pseudonimizacao"
    block: tuple[str, ...] = ()
    unknown_endpoints: str = "bloquear"
    # Servidor
    host: str = "127.0.0.1"
    port: int = 8787
    default_provider: str = "openai"
    playground: bool = True
    audit_log: str | None = None
    session_ttl: int = 3600
    inject_keys: bool = False
    timeout: float = 600.0
    # Se definido, todas as rotas (menos /veu/saude) exigem o cabeçalho X-Veu-Token com este valor.
    token: str | None = None
    # Fora do localhost o servidor exige token; isto libera rodar sem ele (rede interna isolada).
    allow_no_token: bool = False
    max_body_mb: float = 20.0
    # Aceita o cabeçalho X-Veu-Operador para escolher o operador por requisição.
    request_operator: bool = True
    metrics: bool = True
    # Troca links do Notion e do Google (e de outros domínios da lista) pelo conteúdo já protegido.
    expand_links: bool = False
    expand_domains: tuple[str, ...] = ("notion.so", "notion.com", "notion.site", "docs.google.com")
    # "memoria" (padrão) ou uma URL redis://, para várias réplicas do servidor compartilharem as sessões.
    session_backend: str = "memoria"
    # Chave do cofre cifrado no Redis (VEU_CHAVE_COFRE). Sem ela, o Redis só é aceito com permitir_cofre_sem_cifra.
    vault_key: str | None = None
    allow_plain_vault: bool = False
    # Com segredo, cada linha da auditoria leva um HMAC encadeado: alterar ou apagar linhas fica detectável.
    audit_secret: str | None = None
    # Desvio: requisições com estes tipos (vazio = qualquer dado) vão inteiras para um provedor interno.
    route_to: str | None = None
    route_model: str | None = None
    route_labels: tuple[str, ...] = ()
    teams: dict[str, TeamConfig] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=lambda: dict(BUILTIN_PROVIDERS))

    def __post_init__(self):
        for name, value in (("VEU_SEGREDO (segredo_env)", self.secret),
                            ("VEU_SEGREDO_AUDITORIA (segredo_auditoria_env)", self.audit_secret),
                            ("VEU_CHAVE_COFRE (chave_cofre_env)", self.vault_key)):
            if value is not None and len(value) < MIN_SECRET_LENGTH:
                raise ConfigError(
                    f"{name} precisa ter pelo menos {MIN_SECRET_LENGTH} caracteres: um segredo curto pode ser "
                    "adivinhado e revelar os dados por trás dos marcadores. Gere um com: "
                    'python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
        if self.profile not in PROFILES:
            raise ConfigError(f"Perfil desconhecido: {self.profile}. Use um de {', '.join(PROFILES)}.")
        if not 0 <= self.threshold <= 1:
            raise ConfigError("O limiar precisa estar entre 0 e 1.")
        unknown = [label for label in (*self.labels, *self.block, *self.operators) if label not in LABELS
                   and label not in {str(p.get("entidade", "")).upper() for p in self.custom_patterns}]
        if unknown:
            raise ConfigError(f"Entidades desconhecidas: {', '.join(unknown)}. Válidas: {', '.join(LABELS)}.")
        normalize_operator(self.operator)
        for operator in self.operators.values():
            normalize_operator(operator)
        bad = [name for name in self.detectors if name not in DETECTORS and ":" not in name]
        if bad and set(bad) - plugin_detectors():
            raise ConfigError(
                f"Detectores desconhecidos: {', '.join(bad)}. Use um de {', '.join(DETECTORS)}, um plugin instalado "
                'ou um caminho de importação como "meu_pacote.detectores:MeuDetector".'
            )
        for pattern in self.allow_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f'Padrão inválido em ignorar_padroes "{pattern}": {exc}') from exc
        if self.route_to is not None and self.route_to not in self.providers:
            raise ConfigError(f'desviar_para: o provedor "{self.route_to}" não existe.')
        bad_route = [label for label in self.route_labels if label not in LABELS]
        if bad_route:
            raise ConfigError(f"desviar_tipos: entidades desconhecidas: {', '.join(bad_route)}.")
        if not (self.session_backend == "memoria" or self.session_backend.startswith(("redis://", "rediss://"))):
            raise ConfigError('sessoes deve ser "memoria" ou uma URL redis:// (ou rediss://).')
        if self.session_backend != "memoria" and not self.vault_key and not self.allow_plain_vault:
            raise ConfigError(
                "Sessões no Redis guardam os dados reais: defina VEU_CHAVE_COFRE (pelo menos 32 caracteres) para o "
                "cofre ser cifrado, ou permitir_cofre_sem_cifra = true num Redis isolado."
            )
        for team in self.teams.values():
            if not team.token:
                raise ConfigError(f"[equipes.{team.name}] está sem token: defina a variável de token_env.")
            if team.operator:
                normalize_operator(team.operator)
            unknown_block = [label for label in team.block or () if label not in LABELS]
            if unknown_block:
                raise ConfigError(f"[equipes.{team.name}] bloquear: entidades desconhecidas: {', '.join(unknown_block)}.")
        if self.unknown_endpoints not in ("bloquear", "repassar"):
            raise ConfigError('endpoints_desconhecidos deve ser "bloquear" ou "repassar".')
        if self.default_provider not in self.providers:
            raise ConfigError(f'Provedor padrão "{self.default_provider}" não existe.')
        for provider in self.providers.values():
            if provider.kind not in PROVIDER_KINDS:
                raise ConfigError(f'Provedor "{provider.name}": tipo deve ser um de {", ".join(PROVIDER_KINDS)}.')
            if provider.operator:
                normalize_operator(provider.operator)
            unknown_block = [label for label in provider.block or () if label not in LABELS]
            if unknown_block:
                raise ConfigError(f'Provedor "{provider.name}": entidades desconhecidas em bloquear: {unknown_block}.')

    def restore_policy(self):
        from veu.vault import RestorePolicy

        hosts = tuple(host.strip().lower().lstrip(".") for host in self.restore_link_hosts if host.strip())
        return RestorePolicy(links=self.restore_links, link_hosts=hosts, tools=self.restore_tools,
                             secrets_in_tools=self.restore_secrets_in_tools,
                             max_per_response=self.restore_max_per_response)

    def with_profile(self, name: str) -> Config:
        """Aplica um perfil por cima desta configuração (usado por --perfil e VEU_PERFIL)."""
        return self.with_overrides(**profile_options(name), profile=name)

    def with_overrides(self, **changes) -> Config:
        allowed = {f.name for f in fields(self)}
        bad = set(changes) - allowed
        if bad:
            raise ConfigError(f"Opções desconhecidas: {', '.join(sorted(bad))}.")
        normalized = {key: tuple(value) if isinstance(value, list) else value for key, value in changes.items()}
        return replace(self, **normalized)


# Chaves do veu.toml -> campos de Config.
_SECTIONS = {
    "deteccao": {
        "limiar": "threshold", "entidades": "labels", "ignorar": "allowlist", "detectores": "detectors",
        "personalizados": "custom_patterns", "modelo_spacy": "spacy_model", "llm": None,
        "ignorar_padroes": "allow_patterns", "cache": "detection_cache", "modelo_ml": "ml_model",
    },
    "anonimizacao": {
        "operador": "operator", "operadores": "operators", "instruir_modelo": "instruct_model",
        "vincular_nomes": "link_names", "segredo_env": None,
    },
    "restauracao": {
        "links": "restore_links", "dominios_links": "restore_link_hosts", "ferramentas": "restore_tools",
        "segredos_em_ferramentas": "restore_secrets_in_tools", "max_por_resposta": "restore_max_per_response",
    },
    "politica": {
        "perfil": "profile", "bloquear": "block", "endpoints_desconhecidos": "unknown_endpoints", "desviar_para": "route_to",
        "modelo_desvio": "route_model", "desviar_tipos": "route_labels",
    },
    "servidor": {
        "host": "host", "porta": "port", "provedor_padrao": "default_provider", "playground": "playground",
        "log_auditoria": "audit_log", "sessao_ttl": "session_ttl", "injetar_chaves": "inject_keys",
        "timeout": "timeout", "token_env": None, "permitir_sem_token": "allow_no_token",
        "limite_corpo_mb": "max_body_mb", "operador_por_requisicao": "request_operator", "metricas": "metrics",
        "expandir_links": "expand_links", "dominios_expandidos": "expand_domains", "sessoes": "session_backend",
        "segredo_auditoria_env": None, "chave_cofre_env": None, "permitir_cofre_sem_cifra": "allow_plain_vault",
    },
}


_PROVIDER_KEYS = {"tipo", "url", "chave_env", "anonimizar", "operador", "bloquear"}
_TEAM_KEYS = {"token_env", "bloquear", "operador"}


def _team_from_toml(name: str, options: dict) -> TeamConfig:
    extra = set(options) - _TEAM_KEYS
    if extra:
        raise ConfigError(f"[equipes.{name}] não aceita {', '.join(sorted(extra))}. Opções: {', '.join(sorted(_TEAM_KEYS))}.")
    if "token_env" not in options:
        raise ConfigError(f"[equipes.{name}] precisa de token_env (a variável de ambiente com o token da equipe).")
    block = options.get("bloquear")
    return TeamConfig(
        name, os.environ.get(options["token_env"]) or None,
        tuple(label.upper() for label in block) if block is not None else None, options.get("operador"),
    )


def _provider_from_toml(name: str, options: dict, existing: ProviderConfig | None) -> ProviderConfig:
    """[provedores.NOME]: cria um provedor novo (url obrigatória) ou ajusta um já conhecido."""
    extra = set(options) - _PROVIDER_KEYS
    if extra:
        raise ConfigError(f"[provedores.{name}] não aceita {', '.join(sorted(extra))}. "
                          f"Opções: {', '.join(sorted(_PROVIDER_KEYS))}.")
    if existing is None and "url" not in options:
        raise ConfigError(f"[provedores.{name}] é um provedor novo: informe a url.")
    base = existing or ProviderConfig(name, "openai", "")
    block = options.get("bloquear", base.block)
    return replace(
        base,
        kind=options.get("tipo", base.kind),
        url=options.get("url", base.url).rstrip("/"),
        key_env=options.get("chave_env", base.key_env),
        anonymize=bool(options.get("anonimizar", base.anonymize)),
        operator=options.get("operador", base.operator),
        block=tuple(label.upper() for label in block) if block is not None else None,
    )


def _from_toml(data: dict, base: Config) -> dict:
    changes: dict = {}
    # O perfil vem primeiro: as opções escritas no arquivo valem mais que as dele.
    profile = (data.get("politica") or {}).get("perfil")
    if profile:
        changes.update(profile_options(profile))
    for section, values in data.items():
        if section == "equipes":
            changes["teams"] = {name: _team_from_toml(name, options) for name, options in values.items()}
            continue
        if section == "provedores":
            providers = dict(base.providers)
            for name, options in values.items():
                providers[name] = _provider_from_toml(name, options, providers.get(name))
            changes["providers"] = providers
            continue
        mapping = _SECTIONS.get(section)
        if mapping is None:
            raise ConfigError(f"Seção desconhecida no veu.toml: [{section}].")
        for key, value in values.items():
            if key not in mapping:
                raise ConfigError(f"Opção desconhecida: [{section}] {key}.")
            if key == "llm":
                changes.update(llm_url=value.get("url"), llm_model=value.get("modelo"),
                               llm_key_env=value.get("chave_env"))
            elif key == "segredo_env":
                changes["secret"] = os.environ.get(value)
            elif key == "token_env":
                changes["token"] = os.environ.get(value)
            elif key == "segredo_auditoria_env":
                changes["audit_secret"] = os.environ.get(value)
            elif key == "chave_cofre_env":
                changes["vault_key"] = os.environ.get(value)
            elif key == "operadores":
                changes["operators"] = {label.upper(): op for label, op in value.items()}
            elif key in ("entidades", "bloquear", "desviar_tipos"):
                changes[mapping[key]] = [label.upper() for label in value]
            else:
                changes[mapping[key]] = value
    return changes


def _from_env(environ: dict[str, str], base: Config) -> dict:
    changes: dict = {}

    def as_list(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    if environ.get("VEU_PERFIL"):
        changes.update(profile_options(environ["VEU_PERFIL"]), profile=environ["VEU_PERFIL"])
    if "VEU_LIMIAR" in environ:
        changes["threshold"] = float(environ["VEU_LIMIAR"])
    if "VEU_OPERADOR" in environ:
        changes["operator"] = environ["VEU_OPERADOR"]
    if "VEU_BLOQUEAR" in environ:
        changes["block"] = [label.upper() for label in as_list(environ["VEU_BLOQUEAR"])]
    if "VEU_ENTIDADES" in environ:
        changes["labels"] = [label.upper() for label in as_list(environ["VEU_ENTIDADES"])]
    if "VEU_DETECTORES" in environ:
        changes["detectors"] = as_list(environ["VEU_DETECTORES"])
    if "VEU_HOST" in environ:
        changes["host"] = environ["VEU_HOST"]
    if "VEU_PORTA" in environ:
        changes["port"] = int(environ["VEU_PORTA"])
    if "VEU_PROVEDOR_PADRAO" in environ:
        changes["default_provider"] = environ["VEU_PROVEDOR_PADRAO"]
    if "VEU_PLAYGROUND" in environ:
        changes["playground"] = environ["VEU_PLAYGROUND"].strip().lower() in ("1", "true", "sim", "yes")
    if "VEU_LOG_AUDITORIA" in environ:
        changes["audit_log"] = environ["VEU_LOG_AUDITORIA"] or None
    if "VEU_SEGREDO" in environ:
        changes["secret"] = environ["VEU_SEGREDO"]
    if "VEU_TOKEN" in environ:
        changes["token"] = environ["VEU_TOKEN"] or None
    if "VEU_PERMITIR_SEM_TOKEN" in environ:
        changes["allow_no_token"] = environ["VEU_PERMITIR_SEM_TOKEN"].strip().lower() in ("1", "true", "sim", "yes")
    if "VEU_SESSOES" in environ:
        changes["session_backend"] = environ["VEU_SESSOES"] or "memoria"
    if "VEU_SEGREDO_AUDITORIA" in environ:
        changes["audit_secret"] = environ["VEU_SEGREDO_AUDITORIA"] or None
    if "VEU_CHAVE_COFRE" in environ:
        changes["vault_key"] = environ["VEU_CHAVE_COFRE"] or None
    if "VEU_LIMITE_CORPO_MB" in environ:
        changes["max_body_mb"] = float(environ["VEU_LIMITE_CORPO_MB"])
    providers = dict(changes.get("providers", base.providers))
    for name, provider in list(providers.items()):
        env_name = "VEU_URL_" + name.upper().replace("-", "_")
        if env_name in environ:
            providers[name] = replace(provider, url=environ[env_name].rstrip("/"))
    if providers != base.providers:
        changes["providers"] = providers
    return changes


def load_config(path: str | os.PathLike | None = None, environ: dict[str, str] | None = None) -> Config:
    """Carrega o veu.toml (de path, de VEU_CONFIG ou da pasta atual) e aplica as variáveis VEU_*."""
    environ = dict(os.environ if environ is None else environ)
    config = Config()
    candidate = path or environ.get("VEU_CONFIG")
    if candidate is None and Path("veu.toml").is_file():
        candidate = "veu.toml"
    if candidate is not None:
        file = Path(candidate)
        if not file.is_file():
            raise ConfigError(f"Arquivo de configuração não encontrado: {file}")
        with file.open("rb") as handle:
            data = tomllib.load(handle)
        config = config.with_overrides(**_from_toml(data, config))
    return config.with_overrides(**_from_env(environ, config))
