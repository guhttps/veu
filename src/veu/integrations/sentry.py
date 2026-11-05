"""Remove dados pessoais dos eventos enviados ao Sentry (mensagens, exceções, breadcrumbs, request, extras).

    import sentry_sdk
    from veu.integrations.sentry import before_send, before_breadcrumb

    sentry_sdk.init(dsn="...", before_send=before_send, before_breadcrumb=before_breadcrumb)

Não depende do pacote sentry_sdk: as funções recebem e devolvem os dicts dos eventos.
"""

from __future__ import annotations

from typing import Any

from veu.core import Veu

# Campos técnicos que não têm dados pessoais e não precisam ser analisados.
_SKIP_KEYS = frozenset({
    "event_id", "timestamp", "start_timestamp", "platform", "level", "logger", "sdk", "release", "environment",
    "server_name", "modules", "fingerprint", "type", "module", "function", "filename", "lineno", "colno",
    "in_app", "abs_path", "context_line", "pre_context", "post_context", "trace_id", "span_id", "parent_span_id",
    "op", "status", "contexts",
})


class SentryScrubber:
    """Callable para before_send e before_breadcrumb. Por padrão troca os dados por [CPF], [PESSOA]..."""

    def __init__(self, veu: Veu | None = None, operator: str = "remover"):
        self._veu = veu
        self._operator = operator

    @property
    def veu(self) -> Veu:
        if self._veu is None:
            self._veu = Veu(operator=self._operator)
        return self._veu

    def scrub(self, value: Any, key: str | None = None) -> Any:
        if key in _SKIP_KEYS and key != "contexts":
            return value
        if isinstance(value, str):
            return self.veu.anonymize(value).text if value else value
        if isinstance(value, dict):
            return {k: self.scrub(v, k if isinstance(k, str) else None) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.scrub(item) for item in value)
        return value

    def __call__(self, event: dict, hint: dict | None = None) -> dict:
        contexts = event.get("contexts")
        scrubbed = self.scrub(event)
        if isinstance(contexts, dict):
            # Contextos (navegador, sistema, runtime) quase sempre são técnicos; só "user" e "extra" interessam.
            scrubbed["contexts"] = {name: self.scrub(data) if name in ("user", "extra") else data
                                    for name, data in contexts.items()}
        return scrubbed


_default = SentryScrubber()


def before_send(event: dict, hint: dict | None = None) -> dict:
    return _default(event, hint)


def before_breadcrumb(breadcrumb: dict, hint: dict | None = None) -> dict:
    return _default(breadcrumb, hint)
