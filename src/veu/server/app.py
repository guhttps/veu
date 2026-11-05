"""Servidor do Véu: proxy para as APIs de IA, API REST e playground."""

from __future__ import annotations

import contextlib
import hmac
import os
import re
import time
from collections import Counter
from importlib import resources

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from veu import __version__
from veu.anonymizer import normalize_operator
from veu.config import Config, ProviderConfig, load_config
from veu.core import Veu
from veu.gateway import BlockedError, Gateway, detect_adapter
from veu.server.state import AuditLog, SessionStore, Stats

HOP_HEADERS = frozenset({
    "host", "content-length", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "trailers", "transfer-encoding", "upgrade", "accept-encoding",
})
RESPONSE_DROP = frozenset({"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"})
_GEMINI_PATH = re.compile(r":(?:streamGenerateContent|generateContent|countTokens|embedContent|batchEmbedContents)$")


def _error(message: str, status: int, kind: str = "veu_erro") -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": kind}}, status_code=status)


def resolve_route(path: str, config: Config) -> tuple[ProviderConfig, str] | None:
    """Escolhe o provedor pelo prefixo (/groq/v1/...) ou pelo formato do caminho e monta a URL de destino."""
    first, _, rest = path.lstrip("/").partition("/")
    if first in config.providers:
        provider, remainder = config.providers[first], "/" + rest
    else:
        remainder = path
        if path.startswith("/v1beta/") or _GEMINI_PATH.search(path):
            kind = "gemini"
        elif re.search(r"/v1/messages(?:/count_tokens)?/?$", path):
            kind = "anthropic"
        else:
            kind = None
        if kind is None:
            provider = config.providers[config.default_provider]
        else:
            provider = config.providers.get(kind) or next(
                (p for p in config.providers.values() if p.kind == kind), None
            )
            if provider is None:
                return None
    if provider.kind == "openai" and (remainder == "/v1" or remainder.startswith("/v1/")):
        remainder = remainder[3:]
    return provider, provider.url + remainder


def _forward_headers(request: Request, provider: ProviderConfig, config: Config) -> dict[str, str]:
    headers = {
        name: value for name, value in request.headers.items()
        if name.lower() not in HOP_HEADERS and not name.lower().startswith("x-veu-")
    }
    headers["accept-encoding"] = "identity"
    if config.inject_keys and provider.key_env and os.environ.get(provider.key_env):
        key = os.environ[provider.key_env]
        lower = {name.lower() for name in headers}
        if provider.kind == "anthropic" and "x-api-key" not in lower and "authorization" not in lower:
            headers["x-api-key"] = key
        elif provider.kind == "gemini" and "x-goog-api-key" not in lower and "key=" not in request.url.query:
            headers["x-goog-api-key"] = key
        elif provider.kind == "openai" and "authorization" not in lower:
            headers["authorization"] = f"Bearer {key}"
    return headers


def _response_headers(response: httpx.Response, counts: Counter[str] | None = None) -> dict[str, str]:
    headers = {name: value for name, value in response.headers.items() if name.lower() not in RESPONSE_DROP}
    headers["x-veu-versao"] = __version__
    if counts:
        headers["x-veu-entidades"] = ", ".join(f"{label}={count}" for label, count in sorted(counts.items()))
    return headers


def create_app(config: Config | None = None, *, upstream_transport: httpx.AsyncBaseTransport | None = None) -> Starlette:
    config = config or load_config()
    veu = Veu(config)
    gateway = Gateway(veu)
    sessions = SessionStore(veu.new_vault, ttl=config.session_ttl)
    stats = Stats()
    audit = AuditLog(config.audit_log)
    operator_instances: dict[str, Veu] = {config.operator: veu}
    client = httpx.AsyncClient(
        transport=upstream_transport,
        timeout=httpx.Timeout(config.timeout, connect=15.0),
        follow_redirects=False,
    )

    def authorized(request: Request) -> bool:
        if not config.token:
            return True
        given = request.headers.get("x-veu-token", "")
        return hmac.compare_digest(given.encode(), config.token.encode())

    def veu_for(operator: str | None) -> Veu:
        key = normalize_operator(operator) if operator else config.operator
        if key not in operator_instances:
            operator_instances[key] = Veu(config, operator=key)
        return operator_instances[key]

    async def read_json(request: Request) -> dict:
        try:
            data = await request.json()
        except ValueError as exc:
            raise ValueError("O corpo precisa ser um JSON válido.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("texto"), str):
            raise ValueError('Envie um JSON com o campo "texto".')
        return data

    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "versao": __version__})

    async def statistics(request: Request) -> Response:
        if not authorized(request):
            return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        return JSONResponse(stats.snapshot(len(sessions)))

    async def detect(request: Request) -> Response:
        if not authorized(request):
            return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        try:
            data = await read_json(request)
        except ValueError as exc:
            return _error(str(exc), 400)
        entities = veu.analyze(data["texto"])
        return JSONResponse({"entidades": [entity.to_dict() for entity in entities]})

    async def anonymize(request: Request) -> Response:
        if not authorized(request):
            return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        try:
            data = await read_json(request)
            instance = veu_for(data.get("operador"))
        except ValueError as exc:
            return _error(str(exc), 400)
        session_id = data.get("sessao") or SessionStore.new_id()
        vault = sessions.get(session_id)
        result = instance.anonymize(data["texto"], vault)
        stats.record("api", result.counts())
        return JSONResponse({
            "texto": result.text,
            "sessao": session_id,
            "substituicoes": [item.to_dict() for item in result.replacements],
        })

    async def restore(request: Request) -> Response:
        if not authorized(request):
            return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        try:
            data = await read_json(request)
        except ValueError as exc:
            return _error(str(exc), 400)
        vault = sessions.get(str(data.get("sessao") or ""), create=False)
        if vault is None:
            return _error("Sessão não encontrada ou expirada.", 404, "veu_sessao_inexistente")
        return JSONResponse({"texto": vault.restore(data["texto"])})

    async def playground(request: Request) -> Response:
        page = resources.files("veu.server").joinpath("static", "playground.html").read_text(encoding="utf-8")
        return HTMLResponse(page.replace("{{VERSAO}}", __version__).replace("{{TOKEN}}", "1" if config.token else ""))

    async def home(request: Request) -> Response:
        if config.playground:
            return RedirectResponse("/veu/playground")
        return JSONResponse({"veu": __version__, "documentacao": "https://github.com/guhttps/veu#readme"})

    async def passthrough(request: Request, url: str, headers: dict[str, str], body: bytes) -> Response:
        upstream = client.build_request(request.method, url, headers=headers, content=body or None,
                                        params=request.query_params)
        response = await client.send(upstream, stream=True)

        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(chunks(), status_code=response.status_code, headers=_response_headers(response))

    async def proxy(request: Request) -> Response:
        if not authorized(request):
            return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        route = resolve_route(request.url.path, config)
        if route is None:
            return _error("Nenhum provedor configurado para este caminho.", 404, "veu_rota_inexistente")
        provider, url = route
        body = await request.body()
        headers = _forward_headers(request, provider, config)
        adapter = detect_adapter(request.method, url.split("?", 1)[0])
        started = time.monotonic()
        if adapter is None:
            if request.method in ("GET", "HEAD", "OPTIONS") or config.unknown_endpoints == "repassar":
                return await passthrough(request, url, headers, body)
            return _error(
                f"O Véu não sabe esconder dados pessoais de {request.method} {request.url.path}. Para repassar "
                'endpoints desconhecidos sem proteção, use endpoints_desconhecidos = "repassar" no veu.toml.',
                501, "veu_endpoint_nao_suportado",
            )
        session_id = request.headers.get("x-veu-sessao")
        vault = sessions.get(session_id) if session_id else None
        try:
            prepared = gateway.prepare(adapter, body, vault, path=request.url.path)
        except BlockedError as error:
            stats.record(provider.name, error.counts, blocked=True)
            audit.write(provedor=provider.name, endpoint=adapter.name, bloqueado=sorted(error.labels),
                        entidades=dict(error.counts), status=400)
            return JSONResponse(adapter.error_body(str(error)), status_code=400,
                                headers={"x-veu-bloqueado": ",".join(error.labels)})
        except ValueError as error:
            return JSONResponse(adapter.error_body(f"Requisição inválida: {error}"), status_code=400)

        upstream = client.build_request(request.method, url, headers=headers, content=prepared.body,
                                        params=request.query_params)
        try:
            response = await client.send(upstream, stream=True)
        except httpx.HTTPError as exc:
            stats.record(provider.name, prepared.counts, error=True)
            return JSONResponse(adapter.error_body(f"Não foi possível acessar o provedor {provider.name}: {exc}"),
                                status_code=502)

        def finish(status: int) -> None:
            stats.record(provider.name, prepared.counts, error=status >= 500)
            audit.write(provedor=provider.name, endpoint=adapter.name, status=status, stream=prepared.stream,
                        entidades=dict(prepared.counts), duracao_ms=round((time.monotonic() - started) * 1000))

        response_headers = _response_headers(response, prepared.counts)
        if "text/event-stream" in response.headers.get("content-type", ""):
            transformer = gateway.stream(prepared)

            async def events():
                try:
                    async for chunk in response.aiter_bytes():
                        output = transformer.feed(chunk)
                        if output:
                            yield output
                    tail = transformer.close()
                    if tail:
                        yield tail
                finally:
                    await response.aclose()
                    finish(response.status_code)

            return StreamingResponse(events(), status_code=response.status_code, headers=response_headers)

        content = await response.aread()
        await response.aclose()
        if "json" in response.headers.get("content-type", "") or content.startswith((b"{", b"[")):
            content = gateway.restore_body(prepared, content)
        finish(response.status_code)
        return Response(content, status_code=response.status_code, headers=response_headers)

    routes = [
        Route("/veu/saude", health, methods=["GET"]),
        Route("/veu/estatisticas", statistics, methods=["GET"]),
        Route("/veu/v1/detectar", detect, methods=["POST"]),
        Route("/veu/v1/anonimizar", anonymize, methods=["POST"]),
        Route("/veu/v1/restaurar", restore, methods=["POST"]),
    ]
    if config.playground:
        routes.append(Route("/veu/playground", playground, methods=["GET"]))
    routes.append(Route("/", home, methods=["GET"]))
    routes.append(Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.config = config
    app.state.veu = veu
    app.state.sessions = sessions
    app.state.stats = stats
    return app


def run(config: Config | None = None) -> None:
    import uvicorn

    config = config or load_config()
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")
