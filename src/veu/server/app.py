"""Servidor do Véu: proxy para as APIs de IA, API REST e playground."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import time
from collections import Counter
from importlib import resources
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from veu import __version__
from veu.anonymizer import normalize_operator
from veu.config import Config, ConfigError, ProviderConfig, load_config
from veu.core import Veu
from veu.gateway import BlockedError, Gateway, detect_adapter
from veu.server.state import AuditLog, SessionStore, Stats

HOP_HEADERS = frozenset({
    "host", "content-length", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "trailers", "transfer-encoding", "upgrade", "accept-encoding", "origin", "referer", "cookie",
})
RESPONSE_DROP = frozenset({
    "content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive", "set-cookie",
})
LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})
CREDENTIAL_HEADERS = ("authorization", "x-api-key", "x-goog-api-key", "api-key")
_GEMINI_PATH = re.compile(r":(?:streamGenerateContent|generateContent|countTokens|embedContent|batchEmbedContents)$")


def _error(message: str, status: int, kind: str = "veu_erro") -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": kind}}, status_code=status)


def is_local_host(host: str) -> bool:
    return host in LOCAL_HOSTNAMES or host.startswith("127.")


class BodyTooLarge(Exception):
    pass


def resolve_route(path: str, config: Config) -> tuple[ProviderConfig, str] | None:
    """Escolhe o provedor pelo prefixo (/groq/v1/...) ou pelo formato do caminho e monta a URL de destino.

    O destino é sempre a URL configurada do provedor mais o caminho: o cliente não consegue trocar o host.
    """
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
    if not remainder.startswith("/"):
        remainder = "/" + remainder
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
        elif provider.kind == "gemini" and "x-goog-api-key" not in lower and "key" not in request.query_params:
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


def _credential(request: Request) -> str:
    """Identifica quem chama, para que sessões de credenciais diferentes nunca compartilhem o cofre."""
    for name in CREDENTIAL_HEADERS:
        if request.headers.get(name):
            return f"{name}:{request.headers[name]}"
    return f"key:{request.query_params.get('key', '')}"


def create_app(config: Config | None = None, *, upstream_transport: httpx.AsyncBaseTransport | None = None) -> Starlette:
    config = config or load_config()
    exposed = not is_local_host(config.host)
    if exposed and not config.token and not config.allow_no_token:
        raise ConfigError(
            f"O Véu vai ouvir em {config.host}, fora do localhost, sem token. Defina VEU_TOKEN (recomendado) ou, "
            "numa rede interna isolada, VEU_PERMITIR_SEM_TOKEN=1."
        )
    veu = Veu(config)
    gateway = Gateway(veu)
    # Proxy e API REST têm sessões separadas: um identificador escolhido no proxy nunca é restaurável pela API.
    proxy_sessions = SessionStore(veu.new_vault, ttl=config.session_ttl)
    api_sessions = SessionStore(veu.new_vault, ttl=config.session_ttl)
    stats = Stats()
    audit = AuditLog(config.audit_log)
    operator_instances: dict[str, Veu] = {config.operator: veu}
    max_body = int(config.max_body_mb * 1024 * 1024)
    client = httpx.AsyncClient(
        transport=upstream_transport,
        timeout=httpx.Timeout(config.timeout, connect=15.0),
        follow_redirects=False,
    )

    def guard(request: Request, *, check_token: bool = True) -> Response | None:
        """Barra DNS rebinding, requisições de outros sites (CSRF) e chamadas sem o token."""
        host_header = request.headers.get("host", "")
        hostname = urlsplit(f"//{host_header}").hostname or ""
        if not exposed and not is_local_host(hostname):
            return _error("Host não permitido. Acesse o Véu por localhost ou 127.0.0.1.", 403, "veu_host_invalido")
        # Com token, outro site não consegue mandar o X-Veu-Token; sem ele, a origem precisa ser o próprio Véu.
        origin = request.headers.get("origin")
        cross_site = origin is not None and (origin == "null" or urlsplit(origin).netloc != host_header)
        if cross_site and not (exposed and config.token):
            return _error("Requisições de outros sites não são aceitas.", 403, "veu_origem_invalida")
        if check_token and config.token:
            given = request.headers.get("x-veu-token", "")
            if not hmac.compare_digest(given.encode(), config.token.encode()):
                return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        return None

    async def read_body(request: Request) -> bytes:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_body:
            raise BodyTooLarge
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > max_body:
                raise BodyTooLarge
            chunks.append(chunk)
        return b"".join(chunks)

    def too_large() -> JSONResponse:
        return _error(f"Corpo maior que o limite de {config.max_body_mb:g} MB (limite_corpo_mb).", 413,
                      "veu_corpo_grande")

    def veu_for(operator: str | None) -> Veu:
        key = normalize_operator(operator) if operator else config.operator
        if key not in operator_instances:
            operator_instances[key] = Veu(config, operator=key)
        return operator_instances[key]

    async def read_json(request: Request) -> dict:
        import json

        try:
            data = json.loads(await read_body(request))
        except (ValueError, RecursionError) as exc:
            raise ValueError("O corpo precisa ser um JSON válido.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("texto"), str):
            raise ValueError('Envie um JSON com o campo "texto".')
        return data

    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "versao": __version__})

    async def statistics(request: Request) -> Response:
        return guard(request) or JSONResponse(stats.snapshot(len(proxy_sessions) + len(api_sessions)))

    async def detect(request: Request) -> Response:
        if (blocked := guard(request)) is not None:
            return blocked
        try:
            data = await read_json(request)
        except BodyTooLarge:
            return too_large()
        except ValueError as exc:
            return _error(str(exc), 400)
        entities = await run_in_threadpool(veu.analyze, data["texto"])
        return JSONResponse({"entidades": [entity.to_dict() for entity in entities]})

    async def anonymize(request: Request) -> Response:
        if (blocked := guard(request)) is not None:
            return blocked
        try:
            data = await read_json(request)
            instance = veu_for(data.get("operador"))
        except BodyTooLarge:
            return too_large()
        except ValueError as exc:
            return _error(str(exc), 400)
        if data.get("sessao"):
            # Só continua sessões criadas pelo servidor: identificadores escolhidos pelo cliente seriam adivinháveis.
            session_id = str(data["sessao"])
            vault = api_sessions.get(session_id, create=False)
            if vault is None:
                return _error("Sessão não encontrada ou expirada. Omita \"sessao\" para criar uma nova.", 404,
                              "veu_sessao_inexistente")
        else:
            session_id = SessionStore.new_id()
            vault = api_sessions.get(session_id)
        result = await run_in_threadpool(instance.anonymize, data["texto"], vault)
        stats.record("api", result.counts())
        return JSONResponse({
            "texto": result.text,
            "sessao": session_id,
            "substituicoes": [item.to_dict() for item in result.replacements],
        })

    async def restore(request: Request) -> Response:
        if (blocked := guard(request)) is not None:
            return blocked
        try:
            data = await read_json(request)
        except BodyTooLarge:
            return too_large()
        except ValueError as exc:
            return _error(str(exc), 400)
        vault = api_sessions.get(str(data.get("sessao") or ""), create=False)
        if vault is None:
            return _error("Sessão não encontrada ou expirada.", 404, "veu_sessao_inexistente")
        return JSONResponse({"texto": await run_in_threadpool(vault.restore, data["texto"])})

    async def playground(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        page = resources.files("veu.server").joinpath("static", "playground.html").read_text(encoding="utf-8")
        html = page.replace("{{VERSAO}}", __version__).replace("{{TOKEN}}", "1" if config.token else "")
        return HTMLResponse(html, headers={
            "content-security-policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                       "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
        })

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
        if (blocked := guard(request)) is not None:
            return blocked
        route = resolve_route(request.url.path, config)
        if route is None:
            return _error("Nenhum provedor configurado para este caminho.", 404, "veu_rota_inexistente")
        provider, url = route
        try:
            body = await read_body(request)
        except BodyTooLarge:
            return too_large()
        headers = _forward_headers(request, provider, config)
        adapter = detect_adapter(request.method, url.split("?", 1)[0])
        started = time.monotonic()
        if adapter is None:
            if request.method in ("GET", "HEAD") or config.unknown_endpoints == "repassar":
                return await passthrough(request, url, headers, body)
            return _error(
                f"O Véu não sabe esconder dados pessoais de {request.method} {request.url.path}. Para repassar "
                'endpoints desconhecidos sem proteção, use endpoints_desconhecidos = "repassar" no veu.toml.',
                501, "veu_endpoint_nao_suportado",
            )
        vault = None
        session_id = request.headers.get("x-veu-sessao")
        if session_id:
            key = hashlib.sha256(f"{_credential(request)}\0{session_id}".encode()).hexdigest()
            vault = proxy_sessions.get(key)
        try:
            prepared = await run_in_threadpool(gateway.prepare, adapter, body, vault, request.url.path)
        except BlockedError as error:
            stats.record(provider.name, error.counts, blocked=True)
            audit.write(provedor=provider.name, endpoint=adapter.name, bloqueado=sorted(error.labels),
                        entidades=dict(error.counts), status=400)
            return JSONResponse(adapter.error_body(str(error)), status_code=400,
                                headers={"x-veu-bloqueado": ",".join(error.labels)})
        except (ValueError, RecursionError) as error:
            return JSONResponse(adapter.error_body(f"Requisição inválida: {str(error)[:200]}"), status_code=400)

        upstream = client.build_request(request.method, url, headers=headers, content=prepared.body,
                                        params=request.query_params)
        try:
            response = await client.send(upstream, stream=True)
        except httpx.HTTPError as exc:
            stats.record(provider.name, prepared.counts, error=True)
            return JSONResponse(
                adapter.error_body(f"Não foi possível acessar o provedor {provider.name} ({type(exc).__name__})."),
                status_code=502,
            )

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
            content = await run_in_threadpool(gateway.restore_body, prepared, content)
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
    app.state.stats = stats
    return app


def run(config: Config | None = None) -> None:
    import sys

    import uvicorn

    config = config or load_config()
    app = create_app(config)
    print(f"Véu {__version__} em http://{config.host}:{config.port}  (playground: /veu/playground)", file=sys.stderr)
    # Sem log de acesso: a URL pode trazer a chave da API (?key= do Gemini). A auditoria do Véu não grava valores.
    uvicorn.run(app, host=config.host, port=config.port, log_level="info", access_log=False)
