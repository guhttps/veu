"""Sessões, estatísticas e log de auditoria do servidor."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import Counter, OrderedDict
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


class Stats:
    def __init__(self):
        self.started = time.time()
        self.requests = 0
        self.blocked = 0
        self.errors = 0
        self.entities: Counter[str] = Counter()
        self.providers: Counter[str] = Counter()
        self._lock = threading.Lock()

    def record(self, provider: str, counts: Counter[str], *, blocked: bool = False, error: bool = False) -> None:
        with self._lock:
            self.requests += 1
            self.blocked += int(blocked)
            self.errors += int(error)
            self.entities.update(counts)
            self.providers[provider] += 1

    def snapshot(self, sessions: int) -> dict:
        with self._lock:
            return {
                "requisicoes": self.requests,
                "bloqueadas": self.blocked,
                "erros_upstream": self.errors,
                "dados_escondidos": sum(self.entities.values()),
                "por_entidade": dict(self.entities.most_common()),
                "por_provedor": dict(self.providers.most_common()),
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
                "# HELP veu_sessoes_ativas Sessões com cofre na memória.",
                "# TYPE veu_sessoes_ativas gauge",
                f"veu_sessoes_ativas {sessions}",
                "# HELP veu_ativo_desde_segundos Momento em que o servidor iniciou (epoch).",
                "# TYPE veu_ativo_desde_segundos gauge",
                f"veu_ativo_desde_segundos {self.started:.0f}",
            ]
        return "\n".join(lines) + "\n"


class AuditLog:
    """Uma linha JSON por requisição, só com contagens: nenhum valor pessoal é gravado."""

    def __init__(self, path: str | None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()

    def write(self, **fields) -> None:
        if self.path is None:
            return
        record = {"quando": datetime.now(UTC).isoformat(timespec="milliseconds"), **fields}
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
