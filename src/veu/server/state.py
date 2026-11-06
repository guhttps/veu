"""Sessões (na memória ou no Redis), estatísticas e log de auditoria encadeado do servidor."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from veu.vault import Vault


class SessionStore:
    """Cofres por sessão (cabeçalho X-Veu-Sessao), para manter os marcadores entre requisições.

    Os cofres expiram após ttl segundos sem uso e ficam só na memória.
    """

    def __init__(self, new_vault, ttl: int = 3600, max_sessions: int = 10_000):
        self._new_vault = new_vault
        self.ttl = ttl
        self.max_sessions = max_sessions
        self._items: OrderedDict[str, tuple[Vault, float]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(18)

    def get(self, session_id: str, create: bool = True) -> Vault | None:
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            item = self._items.get(session_id)
            if item is None:
                if not create:
                    return None
                vault = self._new_vault()
            else:
                vault = item[0]
            self._items[session_id] = (vault, now)
            self._items.move_to_end(session_id)
            while len(self._items) > self.max_sessions:
                self._items.popitem(last=False)
            return vault

    def _purge(self, now: float) -> None:
        while self._items:
            session_id, (_, last_used) = next(iter(self._items.items()))
            if now - last_used <= self.ttl:
                break
            self._items.pop(session_id)

    def __len__(self) -> int:
        return len(self._items)

    @contextlib.contextmanager
    def session(self, session_id: str, create: bool = True) -> Iterator[Vault | None]:
        """Cofre da sessão durante uma requisição (no Redis, com trava e gravação no fim)."""
        yield self.get(session_id, create=create)

    def ping(self) -> bool:
        return True


class RedisSessionStore:
    """Sessões no Redis, para várias réplicas do servidor (pip install "veu[redis]").

    O cofre tem os dados reais: use um Redis interno, com senha e TLS (rediss://). Cada sessão expira após ttl
    segundos sem uso, e uma trava por sessão impede que duas réplicas deem o mesmo marcador a valores diferentes.
    """

    def __init__(self, url: str, new_vault, ttl: int = 3600, prefix: str = "veu:sessao:", client=None):
        if client is None:
            try:
                import redis
            except ImportError as exc:
                raise ImportError('Sessões no Redis precisam do pacote redis: pip install "veu[redis]"') from exc
            client = redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
        self.client = client
        self._new_vault = new_vault
        self.ttl = ttl
        self.prefix = prefix

    @staticmethod
    def new_id() -> str:
        return SessionStore.new_id()

    def _load(self, session_id: str) -> Vault | None:
        raw = self.client.get(self.prefix + session_id)
        if raw is None:
            return None
        vault = Vault.from_dict(json.loads(raw))
        vault._secret = self._new_vault()._secret  # mesmo segredo do operador hash em todas as réplicas
        return vault

    def _save(self, session_id: str, vault: Vault) -> None:
        self.client.set(self.prefix + session_id, json.dumps(vault.to_dict(), ensure_ascii=False), ex=self.ttl)

    def get(self, session_id: str, create: bool = True) -> Vault | None:
        vault = self._load(session_id)
        if vault is not None:
            self.client.expire(self.prefix + session_id, self.ttl)
            return vault
        if not create:
            return None
        vault = self._new_vault()
        self._save(session_id, vault)
        return vault

    @contextlib.contextmanager
    def session(self, session_id: str, create: bool = True) -> Iterator[Vault | None]:
        # Trava simples (SET NX com dono e validade): só uma réplica por vez altera o cofre da sessão.
        lock_key, owner = f"{self.prefix}trava:{session_id}", secrets.token_hex(8)
        deadline = time.monotonic() + 30
        while not self.client.set(lock_key, owner, nx=True, px=60_000):
            if time.monotonic() > deadline:
                raise TimeoutError("Sessão ocupada por outra requisição há muito tempo.")
            time.sleep(0.02)
        try:
            vault = self._load(session_id)
            if vault is None and create:
                vault = self._new_vault()
            yield vault
            if vault is not None:
                self._save(session_id, vault)
        finally:
            with contextlib.suppress(Exception):
                current = self.client.get(lock_key)
                if current in (owner, owner.encode()):
                    self.client.delete(lock_key)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def __len__(self) -> int:
        count = 0
        for key in self.client.scan_iter(match=self.prefix + "*", count=1000):
            if b":trava:" not in (key if isinstance(key, bytes) else key.encode()):
                count += 1
            if count >= 100_000:
                break
        return count


def session_store(backend: str, new_vault, ttl: int, prefix: str):
    if backend.startswith(("redis://", "rediss://")):
        return RedisSessionStore(backend, new_vault, ttl=ttl, prefix=prefix)
    return SessionStore(new_vault, ttl=ttl)


class Stats:
    def __init__(self):
        self.started = time.time()
        self.requests = 0
        self.blocked = 0
        self.errors = 0
        self.entities: Counter[str] = Counter()
        self.providers: Counter[str] = Counter()
        self.teams: Counter[str] = Counter()
        self.routed = 0
        self._lock = threading.Lock()

    def record(self, provider: str, counts: Counter[str], *, blocked: bool = False, error: bool = False,
               team: str | None = None, routed: bool = False) -> None:
        with self._lock:
            self.requests += 1
            self.blocked += int(blocked)
            self.errors += int(error)
            self.routed += int(routed)
            self.entities.update(counts)
            self.providers[provider] += 1
            if team:
                self.teams[team] += 1

    def snapshot(self, sessions: int) -> dict:
        with self._lock:
            return {
                "requisicoes": self.requests,
                "bloqueadas": self.blocked,
                "erros_upstream": self.errors,
                "dados_escondidos": sum(self.entities.values()),
                "por_entidade": dict(self.entities.most_common()),
                "por_provedor": dict(self.providers.most_common()),
                "por_equipe": dict(self.teams.most_common()),
                "desviadas": self.routed,
                "sessoes_ativas": sessions,
                "ativo_desde": datetime.fromtimestamp(self.started, UTC).isoformat(timespec="seconds"),
            }


    def prometheus(self, sessions: int, version: str) -> str:
        """Métricas no formato texto do Prometheus (contadores; nenhum valor pessoal)."""

        def label(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

        with self._lock:
            lines = [
                "# HELP veu_info Versão do Véu.",
                "# TYPE veu_info gauge",
                f'veu_info{{versao="{label(version)}"}} 1',
                "# HELP veu_requisicoes_total Requisições processadas, por provedor.",
                "# TYPE veu_requisicoes_total counter",
                *(f'veu_requisicoes_total{{provedor="{label(name)}"}} {count}' for name, count in sorted(self.providers.items())),
                "# HELP veu_requisicoes_bloqueadas_total Requisições recusadas pela política.",
                "# TYPE veu_requisicoes_bloqueadas_total counter",
                f"veu_requisicoes_bloqueadas_total {self.blocked}",
                "# HELP veu_erros_upstream_total Respostas com erro 5xx ou falha de conexão com o provedor.",
                "# TYPE veu_erros_upstream_total counter",
                f"veu_erros_upstream_total {self.errors}",
                "# HELP veu_dados_escondidos_total Dados pessoais escondidos, por tipo.",
                "# TYPE veu_dados_escondidos_total counter",
                *(f'veu_dados_escondidos_total{{entidade="{label(name)}"}} {count}' for name, count in sorted(self.entities.items())),
                "# HELP veu_requisicoes_por_equipe_total Requisições por equipe (tokens de [equipes]).",
                "# TYPE veu_requisicoes_por_equipe_total counter",
                *(f'veu_requisicoes_por_equipe_total{{equipe="{label(name)}"}} {count}' for name, count in sorted(self.teams.items())),
                "# HELP veu_requisicoes_desviadas_total Requisições enviadas inteiras ao provedor interno (desviar_para).",
                "# TYPE veu_requisicoes_desviadas_total counter",
                f"veu_requisicoes_desviadas_total {self.routed}",
                "# HELP veu_sessoes_ativas Sessões com cofre na memória.",
                "# TYPE veu_sessoes_ativas gauge",
                f"veu_sessoes_ativas {sessions}",
                "# HELP veu_ativo_desde_segundos Momento em que o servidor iniciou (epoch).",
                "# TYPE veu_ativo_desde_segundos gauge",
                f"veu_ativo_desde_segundos {self.started:.0f}",
            ]
        return "\n".join(lines) + "\n"


GENESIS = "0" * 64


def _digest(record: dict, secret: str | None) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if secret:
        return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return hashlib.sha256(canonical).hexdigest()


class AuditLog:
    """Uma linha JSON por requisição, só com contagens: nenhum valor pessoal é gravado.

    As linhas são encadeadas: cada uma traz o hash da anterior ("anterior") e o próprio ("hash"). Com um segredo
    (segredo_auditoria_env), o hash vira um HMAC e quem não tem o segredo não consegue refazer a cadeia depois de
    alterar ou apagar linhas. Confira com: veu auditoria verificar arquivo.jsonl
    path "-" escreve na saída padrão (para coletores de log no Kubernetes).
    """

    def __init__(self, path: str | None, secret: str | None = None):
        self.path = Path(path) if path and path != "-" else None
        self.stdout = path == "-"
        self.secret = secret
        self._lock = threading.Lock()
        self._last = self._last_hash()

    def _last_hash(self) -> str:
        if self.path is None or not self.path.is_file():
            return GENESIS
        with self.path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 65536))
            lines = handle.read().splitlines()
        for raw in reversed(lines):
            with contextlib.suppress(ValueError):
                return json.loads(raw)["hash"]
        return GENESIS

    def write(self, **fields) -> None:
        if self.path is None and not self.stdout:
            return
        with self._lock:
            record = {"quando": datetime.now(UTC).isoformat(timespec="milliseconds"), **fields, "anterior": self._last}
            digest = _digest(record, self.secret)
            line = json.dumps({**record, "hash": digest}, ensure_ascii=False) + "\n"
            if self.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
            else:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            self._last = digest


def verify_audit(path: str | Path, secret: str | None = None) -> tuple[bool, int, str | None]:
    """Confere a cadeia de um log de auditoria. Devolve (íntegro, linhas lidas, problema encontrado)."""
    previous = None
    count = 0
    with Path(path).open(encoding="utf-8") as handle:
        for number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
                digest = record.pop("hash")
            except (ValueError, KeyError):
                return False, count, f"linha {number}: não é um registro de auditoria do Véu"
            if previous is not None and record.get("anterior") != previous:
                return False, count, f"linha {number}: a cadeia foi quebrada (linha removida ou fora de ordem)"
            if not hmac.compare_digest(_digest(record, secret), digest):
                return False, count, f"linha {number}: conteúdo alterado (ou segredo errado)"
            previous = digest
            count += 1
    return True, count, None
