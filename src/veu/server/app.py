"""Servidor do Véu: proxy para as APIs de IA, API REST e playground."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import sys
import time
from collections import Counter
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from veu import __version__
from veu.anonymizer import normalize_operator
from veu.cache import cache_scope
from veu.config import Config, ConfigError, ProviderConfig, load_config
from veu.core import Veu
from veu.gateway import BlockedError, Gateway, detect_adapter, is_streaming
from veu.server.siem import forwarder_from_config
from veu.server.state import AuditLog, SessionStore, Stats, VaultCipher, session_store
from veu.vault import count_restorations

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
        elif re.fullmatch(r"/api/(?:chat|generate|embed|embeddings|tags|show|ps|version)/?", path):
            kind = "ollama"
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


def _scope(request: Request) -> str:
    """Credencial mais a identidade do Véu (equipe ou usuário do OIDC): com as chaves injetadas pelo gateway,
    duas equipes com o mesmo X-Veu-Sessao não podem cair no mesmo cofre."""
    identity = getattr(request.state, "identity", None)
    return _credential(request) + (f"\0{identity}" if identity else "")


def create_app(config: Config | None = None, *, upstream_transport: httpx.AsyncBaseTransport | None = None,
               panel=None) -> Starlette:
    config = config or load_config()
    exposed = not is_local_host(config.host)
    team_tokens = {team.token: team for team in config.teams.values() if team.token}
    oidc = None
    if config.oidc_issuer:
        from veu.server.oidc import OIDCVerifier

        oidc = OIDCVerifier(config.oidc_issuer, config.oidc_audience or "", config.oidc_jwks, background=True)
    protected = bool(config.token or team_tokens or oidc)
    if exposed and not protected and not config.allow_no_token:
        raise ConfigError(
            f"O Véu vai ouvir em {config.host}, fora do localhost, sem token. Defina VEU_TOKEN (recomendado) ou, "
            "numa rede interna isolada, VEU_PERMITIR_SEM_TOKEN=1."
        )
    veu = Veu(config)
    gateways: dict[str, Gateway] = {config.operator: Gateway(veu)}

    def gateway_for(operator: str) -> Gateway:
        if operator not in gateways:
            gateways[operator] = Gateway(veu.with_operator(operator))
        return gateways[operator]

    # Proxy e API REST têm sessões separadas: um identificador escolhido no proxy nunca é restaurável pela API.
    cipher = VaultCipher(config.vault_key) if config.vault_key else None
    proxy_sessions = session_store(config.session_backend, veu.new_vault, config.session_ttl, "veu:proxy:", cipher)
    api_sessions = session_store(config.session_backend, veu.new_vault, config.session_ttl, "veu:api:", cipher)
    stats = Stats()
    siem = forwarder_from_config(config)
    audit = AuditLog(config.audit_log, config.audit_secret, sink=siem.submit if siem else None)

    def log_request(**fields) -> None:
        audit.write(**fields)
        stats.remember(**fields)

    def team_for_claims(claims: dict):
        from veu.server.oidc import claim_values

        groups = claim_values(claims, config.oidc_team_claim)
        return next((team for team in config.teams.values() if groups & set(team.oidc_groups)), None)
    operator_instances: dict[str, Veu] = {config.operator: veu}
    max_body = int(config.max_body_mb * 1024 * 1024)
    client = httpx.AsyncClient(
        transport=upstream_transport,
        timeout=httpx.Timeout(config.timeout, connect=15.0),
        follow_redirects=False,
    )

    def guard(request: Request, *, check_token: bool = True, allow_bearer: bool = False) -> Response | None:
        """Barra DNS rebinding, requisições de outros sites (CSRF) e chamadas sem o token."""
        host_header = request.headers.get("host", "")
        hostname = urlsplit(f"//{host_header}").hostname or ""
        if not exposed and not is_local_host(hostname):
            return _error("Host não permitido. Acesse o Véu por localhost ou 127.0.0.1.", 403, "veu_host_invalido")
        # Com token, outro site não consegue mandar o X-Veu-Token; sem ele, a origem precisa ser o próprio Véu.
        origin = request.headers.get("origin")
        cross_site = origin is not None and (origin == "null" or urlsplit(origin).netloc != host_header)
        if cross_site and not (exposed and protected):
            return _error("Requisições de outros sites não são aceitas.", 403, "veu_origem_invalida")
        request.state.team = None
        request.state.identity = None
        request.state.user = None
        if check_token and protected:
            given = request.headers.get("x-veu-token", "")
            if not given and allow_bearer:
                given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            matched = bool(config.token) and hmac.compare_digest(given.encode(), config.token.encode())
            for token, team in team_tokens.items():  # compara com todos, sem atalho
                if hmac.compare_digest(given.encode(), token.encode()):
                    matched, request.state.team = True, team
                    request.state.identity = f"equipe:{team.name}"
            if not matched and oidc is not None:
                from veu.server.oidc import OIDCError, looks_like_jwt

                if looks_like_jwt(given):
                    try:
                        claims = oidc.verify(given)
                    except OIDCError as exc:
                        return _error(f"Token OIDC recusado: {exc}.", 401, "veu_nao_autorizado")
                    team = team_for_claims(claims)
                    if team is None and config.oidc_require_team:
                        return _error("Seu usuário não está em nenhum grupo com acesso ao Véu ([equipes] grupos_oidc).",
                                      403, "veu_sem_equipe")
                    matched, request.state.team = True, team
                    request.state.identity = f"oidc:{claims.get('iss')}|{claims.get('sub')}"
                    if config.oidc_user_claim and claims.get(config.oidc_user_claim):
                        request.state.user = str(claims[config.oidc_user_claim])[:200]
            if not matched:
                return _error("Token do Véu ausente ou inválido (cabeçalho X-Veu-Token).", 401, "veu_nao_autorizado")
        return None

    def who(request: Request) -> dict:
        """Equipe e, com [oidc] claim_usuario, o usuário: entram na auditoria."""
        user = getattr(request.state, "user", None)
        return {"equipe": team_name(request), **({"usuario": user} if user else {})}

    def team_name(request: Request) -> str | None:
        team = getattr(request.state, "team", None)
        return team.name if team else None

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
            operator_instances[key] = veu.with_operator(key)
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

    async def ready(request: Request) -> Response:
        """Prontidão (Kubernetes): o armazenamento de sessões responde."""
        if await run_in_threadpool(proxy_sessions.ping):
            return JSONResponse({"status": "pronto", "versao": __version__})
        return JSONResponse({"status": "indisponivel", "motivo": "armazenamento de sessões"}, status_code=503)

    async def statistics(request: Request) -> Response:
        return guard(request) or JSONResponse(stats.snapshot(len(proxy_sessions) + len(api_sessions),
                                                             veu.analyzer.cache, siem))

    async def metrics(request: Request) -> Response:
        # O Prometheus envia "Authorization: Bearer <token>"; o X-Veu-Token também vale.
        if (blocked := guard(request, allow_bearer=True)) is not None:
            return blocked
        text = stats.prometheus(len(proxy_sessions) + len(api_sessions), __version__, veu.analyzer.cache, siem)
        return Response(text, media_type="text/plain; version=0.0.4; charset=utf-8")

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
        # Só continua sessões criadas pelo servidor: identificadores escolhidos pelo cliente seriam adivinháveis.
        existing = bool(data.get("sessao"))
        session_id = str(data["sessao"]) if existing else SessionStore.new_id()

        def anonymize_in_session():
            with api_sessions.session(session_id, create=not existing) as vault:
                return None if vault is None else instance.anonymize(data["texto"], vault)

        result = await run_in_threadpool(anonymize_in_session)
        if result is None:
            return _error("Sessão não encontrada ou expirada. Omita \"sessao\" para criar uma nova.", 404,
                          "veu_sessao_inexistente")
        stats.record("api", result.counts(), team=team_name(request))
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
        vault = await run_in_threadpool(api_sessions.get, str(data.get("sessao") or ""), False)
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

    panel_routes: list[Route] = []
    if panel is not None:
        panel_routes = _panel_routes(panel, config, veu, api_sessions, stats, guard, read_body, too_large)

    async def unknown_veu_route(request: Request) -> Response:
        return _error(f"Rota do Véu inexistente ou desligada: {request.url.path}", 404, "veu_rota_inexistente")

    async def home(request: Request) -> Response:
        if panel is not None:
            return RedirectResponse("/veu/painel")
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
        team = getattr(request.state, "team", None)
        if adapter is not None and not provider.anonymize:
            # Provedor configurado com anonimizar = false (por exemplo, um modelo local): repassa sem alterar.
            stats.record(provider.name, Counter(), team=team_name(request))
            log_request(provedor=provider.name, endpoint=adapter.name, sem_anonimizar=True, **who(request))
            return await passthrough(request, url, headers, body)
        if adapter is None:
            if request.method in ("GET", "HEAD") or config.unknown_endpoints == "repassar":
                return await passthrough(request, url, headers, body)
            return _error(
                f"O Véu não sabe esconder dados pessoais de {request.method} {request.url.path}. Para repassar "
                'endpoints desconhecidos sem proteção, use endpoints_desconhecidos = "repassar" no veu.toml.',
                501, "veu_endpoint_nao_suportado",
            )
        operator = (team.operator if team else None) or provider.operator or config.operator
        requested = request.headers.get("x-veu-operador")
        if requested and config.request_operator:
            try:
                operator = normalize_operator(requested)
            except ValueError as error:
                return JSONResponse(adapter.error_body(str(error)), status_code=400)
        gateway = gateway_for(normalize_operator(operator))
        session_id = request.headers.get("x-veu-sessao")
        block = team.block if team is not None and team.block is not None else provider.block

        def prepare():
            # Cada credencial tem o seu espaço no cache de detecção (sem canal de tempo entre clientes).
            with cache_scope(hashlib.sha256(_scope(request).encode()).hexdigest()):
                if not session_id:
                    return gateway.prepare(adapter, body, None, request.url.path, block)
                key = hashlib.sha256(f"{_scope(request)}\0{session_id}".encode()).hexdigest()
                with proxy_sessions.session(key) as vault:
                    return gateway.prepare(adapter, body, vault, request.url.path, block)

        try:
            prepared = await run_in_threadpool(prepare)
        except BlockedError as error:
            stats.record(provider.name, error.counts, blocked=True, team=team_name(request))
            log_request(provedor=provider.name, endpoint=adapter.name, bloqueado=sorted(error.labels),
                        entidades=dict(error.counts), status=400, **who(request))
            return JSONResponse(adapter.error_body(str(error)), status_code=400,
                                headers={"x-veu-bloqueado": ",".join(error.labels)})
        except (ValueError, RecursionError) as error:
            return JSONResponse(adapter.error_body(f"Requisição inválida: {str(error)[:200]}"), status_code=400)

        target = config.providers.get(config.route_to) if config.route_to else None
        sensitive = bool(prepared.counts) and (not config.route_labels or bool(set(prepared.counts) & set(config.route_labels)))
        if target is not None and sensitive and target.kind == provider.kind and provider.kind != "gemini":
            # Desvio: com dados sensíveis, a requisição original vai inteira para o provedor interno.
            original = body
            if config.route_model:
                import json

                payload = json.loads(body or b"{}")
                payload["model"] = config.route_model
                original = json.dumps(payload, ensure_ascii=False).encode()
            routed_headers = {name: value for name, value in headers.items() if name.lower() not in CREDENTIAL_HEADERS}
            if target.key_env and os.environ.get(target.key_env):
                key_value = os.environ[target.key_env]
                if target.kind == "anthropic":
                    routed_headers["x-api-key"] = key_value
                else:
                    routed_headers["authorization"] = f"Bearer {key_value}"
            stats.record(target.name, prepared.counts, routed=True, team=team_name(request))
            log_request(provedor=provider.name, endpoint=adapter.name, desviado_para=target.name,
                        entidades=dict(prepared.counts), **who(request))
            return await passthrough(request, target.url + url[len(provider.url):], routed_headers, original)

        upstream = client.build_request(request.method, url, headers=headers, content=prepared.body,
                                        params=request.query_params)
        try:
            response = await client.send(upstream, stream=True)
        except httpx.HTTPError as exc:
            stats.record(provider.name, prepared.counts, error=True, team=team_name(request))
            return JSONResponse(
                adapter.error_body(f"Não foi possível acessar o provedor {provider.name} ({type(exc).__name__})."),
                status_code=502,
            )

        restored: Counter = Counter()  # valores reais devolvidos nesta resposta, por tipo

        def finish(status: int) -> None:
            stats.record(provider.name, prepared.counts, error=status >= 500, team=team_name(request),
                         restored=restored)
            log_request(provedor=provider.name, endpoint=adapter.name, status=status, stream=prepared.stream,
                        entidades=dict(prepared.counts), restaurados=dict(restored),
                        duracao_ms=round((time.monotonic() - started) * 1000), **who(request))

        response_headers = _response_headers(response, prepared.counts)
        content_type = response.headers.get("content-type", "")
        if is_streaming(content_type):
            transformer = gateway.stream(prepared, content_type)

            async def events():
                try:
                    async for chunk in response.aiter_bytes():
                        with count_restorations(restored):
                            output = transformer.feed(chunk)
                        if output:
                            yield output
                    with count_restorations(restored):
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
            def restore_counted(body: bytes) -> bytes:
                with count_restorations(restored):
                    return gateway.restore_body(prepared, body)

            content = await run_in_threadpool(restore_counted, content)
        finish(response.status_code)
        return Response(content, status_code=response.status_code, headers=response_headers)

    routes = [
        Route("/veu/saude", health, methods=["GET"]),
        Route("/veu/pronto", ready, methods=["GET"]),
        Route("/veu/estatisticas", statistics, methods=["GET"]),
        *([Route("/veu/metricas", metrics, methods=["GET"])] if config.metrics else []),
        Route("/veu/v1/detectar", detect, methods=["POST"]),
        Route("/veu/v1/anonimizar", anonymize, methods=["POST"]),
        Route("/veu/v1/restaurar", restore, methods=["POST"]),
    ]
    if config.playground:
        routes.append(Route("/veu/playground", playground, methods=["GET"]))
    routes.extend(panel_routes)
    routes.append(Route("/", home, methods=["GET"]))
    # Rotas do próprio Véu que não existem (ex.: métricas desligadas) nunca podem cair no proxy.
    routes.append(Route("/veu/{path:path}", unknown_veu_route,
                        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]))
    routes.append(Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if oidc is not None:
            from veu.server.oidc import OIDCError

            try:
                await run_in_threadpool(oidc.prefetch)  # as chaves do emissor já ficam prontas para o primeiro token
            except OIDCError as exc:
                print(f"Aviso: OIDC sem as chaves do emissor por enquanto ({exc}). O Véu tenta de novo sozinho.",
                      file=sys.stderr)
        yield
        await client.aclose()
        if siem is not None:
            await run_in_threadpool(siem.close)

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.config = config
    app.state.veu = veu
    app.state.siem = siem
    app.state.stats = stats
    return app


PANEL_FILES = {
    ".txt": "text/plain", ".md": "text/markdown", ".log": "text/plain", ".csv": "text/csv",
    ".tsv": "text/tab-separated-values", ".json": "application/json", ".jsonl": "application/x-ndjson",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "text/plain",
}
PANEL_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
             "img-src 'self' data:; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")


def _panel_routes(panel, config: Config, veu: Veu, api_sessions, stats: Stats, guard, read_body, too_large) -> list[Route]:
    """Rotas do painel (veu painel): só existem quando o Véu foi aberto pelo painel, sempre no localhost."""
    import json
    import tempfile
    from pathlib import Path
    from urllib.parse import quote

    from starlette.background import BackgroundTask

    from veu import atalhos
    from veu.files import anonymize_file, restore_file
    from veu.server import panel as panel_module

    async def page(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        html = resources.files("veu.server").joinpath("static", "painel.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("{{VERSAO}}", __version__), headers={
            "content-security-policy": PANEL_CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
        })

    async def state(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked

        def collect() -> dict:
            return {
                "versao": __version__,
                "endereco": f"http://127.0.0.1:{config.port}",
                "configuracoes": panel_module.settings_from_config(config),
                "opcoes": {
                    "categorias": panel_module.CATEGORIES, "bloquear": panel_module.BLOCK_OPTIONS,
                    "operadores": panel_module.OPERATORS,
                },
                "estatisticas": stats.snapshot(len(api_sessions)),
                "aplicativos": {app: panel_module.mcp_status(app) for app in panel_module.mcp_apps()},
                "inicializacao": atalhos.autostart_enabled(),
                "arquivo_config": str(panel.config_path),
            }

        return JSONResponse(await run_in_threadpool(collect))

    async def read_payload(request: Request) -> dict:
        try:
            data = json.loads(await read_body(request) or b"{}")
        except ValueError as exc:
            raise ValueError("O corpo precisa ser um JSON válido.") from exc
        if not isinstance(data, dict):
            raise ValueError("O corpo precisa ser um objeto JSON.")
        return data

    async def save(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        try:
            settings = await read_payload(request)
            await run_in_threadpool(panel_module.apply_settings, panel.config_path, settings)
        except ValueError as exc:
            return _error(str(exc), 400)
        # Responde primeiro e depois reinicia com o veu.toml novo.
        return JSONResponse({"ok": True, "reiniciando": True}, background=BackgroundTask(panel.stop, restart=True))

    async def connect_app(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        app = request.path_params["app"]
        if app not in panel_module.mcp_apps():
            return _error("Aplicativo desconhecido.", 404)
        try:
            data = await read_payload(request)
            status = await run_in_threadpool(panel_module.connect_mcp, app, bool(data.get("conectar", True)))
        except (ValueError, OSError) as exc:
            return _error(str(exc), 400)
        return JSONResponse(status)

    async def startup(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        try:
            data = await read_payload(request)
            await run_in_threadpool(atalhos.set_autostart, bool(data.get("ativo")))
        except (ValueError, OSError) as exc:
            return _error(str(exc), 400)
        return JSONResponse({"inicializacao": await run_in_threadpool(atalhos.autostart_enabled)})

    async def shutdown(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        return JSONResponse({"ok": True}, background=BackgroundTask(panel.stop))

    def file_name(request: Request) -> tuple[str, str]:
        name = Path(request.query_params.get("nome", "")).name or "arquivo.txt"
        suffix = Path(name).suffix.lower()
        if suffix not in PANEL_FILES:
            raise ValueError("Formato não suportado. Use Excel, Word, PowerPoint, PDF, CSV, JSON ou texto.")
        return name, suffix

    def download(content: bytes, name: str, suffix: str, headers: dict) -> Response:
        disposition = f"attachment; filename*=UTF-8''{quote(name)}"
        return Response(content, media_type=PANEL_FILES[suffix],
                        headers={"content-disposition": disposition, "cache-control": "no-store", **headers})

    async def protect_file(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        try:
            name, suffix = file_name(request)
            body = await read_body(request)
        except BodyTooLarge:
            return too_large()
        except ValueError as exc:
            return _error(str(exc), 400)
        output_suffix = ".txt" if suffix == ".pdf" else suffix
        session_id = SessionStore.new_id()

        def work() -> tuple[bytes, dict]:
            with tempfile.TemporaryDirectory(prefix="veu-") as folder:
                source, target = Path(folder) / f"entrada{suffix}", Path(folder) / f"saida{output_suffix}"
                source.write_bytes(body)
                with api_sessions.session(session_id) as vault:
                    _, counts = anonymize_file(source, target, veu=veu, vault=vault)
                return target.read_bytes(), dict(counts)

        try:
            content, counts = await run_in_threadpool(work)
        except ImportError as exc:
            return _error(str(exc), 400)
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            return _error(f"Não consegui ler o arquivo: {str(exc)[:200]}", 400)
        stats.record("painel", Counter(counts))
        return download(content, f"{Path(name).stem}-protegido{output_suffix}", output_suffix,
                        {"x-veu-sessao": session_id, "x-veu-escondidos": json.dumps(counts)})

    async def restore_file_route(request: Request) -> Response:
        if (blocked := guard(request, check_token=False)) is not None:
            return blocked
        try:
            name, suffix = file_name(request)
            body = await read_body(request)
        except BodyTooLarge:
            return too_large()
        except ValueError as exc:
            return _error(str(exc), 400)
        if suffix == ".pdf":
            return _error("Para restaurar, use o arquivo de texto gerado a partir do PDF.", 400)
        vault = await run_in_threadpool(api_sessions.get, request.query_params.get("sessao", ""), False)
        if vault is None:
            return _error("Não encontrei os dados deste arquivo. Proteja de novo: o Véu guarda os dados reais "
                          "só enquanto está ligado.", 404, "veu_sessao_inexistente")

        def work() -> bytes:
            with tempfile.TemporaryDirectory(prefix="veu-") as folder:
                source, target = Path(folder) / f"entrada{suffix}", Path(folder) / f"saida{suffix}"
                source.write_bytes(body)
                restore_file(source, target, vault)
                return target.read_bytes()

        try:
            content = await run_in_threadpool(work)
        except (ImportError, ValueError, OSError, UnicodeDecodeError) as exc:
            return _error(f"Não consegui ler o arquivo: {str(exc)[:200]}", 400)
        stem = Path(name).stem.removesuffix("-protegido")
        return download(content, f"{stem}-com-dados{suffix}", suffix, {})

    return [
        Route("/veu/painel", page, methods=["GET"]),
        Route("/veu/painel/estado", state, methods=["GET"]),
        Route("/veu/painel/configuracoes", save, methods=["POST"]),
        Route("/veu/painel/aplicativos/{app}", connect_app, methods=["POST"]),
        Route("/veu/painel/inicializacao", startup, methods=["POST"]),
        Route("/veu/painel/desligar", shutdown, methods=["POST"]),
        Route("/veu/painel/arquivos/proteger", protect_file, methods=["POST"]),
        Route("/veu/painel/arquivos/restaurar", restore_file_route, methods=["POST"]),
    ]


def _already_running(port: int) -> bool:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/veu/saude", timeout=1.5) as response:  # noqa: S310
            return "versao" in json.loads(response.read())
    except (OSError, ValueError):
        return False


def run_panel(open_browser: bool = True, port: int | None = None) -> None:
    """veu painel: liga o Véu no localhost e abre o painel no navegador. Salvar as configurações reinicia o servidor."""
    import sys
    import threading
    import webbrowser

    import uvicorn

    from veu.server.panel import PanelController, user_config_path

    path = user_config_path()
    first = True
    while True:
        try:
            config = load_config(path if path.is_file() else None)
        except ConfigError as exc:
            print(f"Erro no {path}: {exc}\nUsando a configuração padrão.", file=sys.stderr)
            config = Config()
        config = config.with_overrides(host="127.0.0.1", port=port or config.port,
                                       session_ttl=max(config.session_ttl, 12 * 3600))
        url = f"http://127.0.0.1:{config.port}/veu/painel"
        if first and _already_running(config.port):
            print(f"O Véu já está ligado: {url}")
            if open_browser:
                webbrowser.open(url)
            return
        controller = PanelController(path)
        app = create_app(config, panel=controller)
        server = uvicorn.Server(uvicorn.Config(app, host=config.host, port=config.port, log_level="warning",
                                               access_log=False))
        controller.server = server
        if first:
            print(f"\n  Véu {__version__} ligado.\n\n  Painel: {url}\n  Endereço para aplicativos: "
                  f"http://127.0.0.1:{config.port}/v1\n\n  Pode minimizar esta janela. Fechar a janela desliga o Véu.\n")
            if open_browser:
                threading.Timer(1.2, webbrowser.open, [url]).start()
        server.run()
        first = False
        if not controller.restart:
            break
        print("  Configuração salva. Reiniciando o Véu...")


def app_from_environment() -> Starlette:
    """App de cada processo com --workers: a configuração vem do VEU_CONFIG e das variáveis VEU_*.

    Cada processo escreve a sua própria cadeia de auditoria (auditoria.<pid>.jsonl), para todas continuarem
    verificáveis com veu auditoria verificar.
    """
    config = load_config()
    if config.audit_log and config.audit_log != "-":
        path = Path(config.audit_log)
        config = config.with_overrides(audit_log=str(path.with_name(f"{path.stem}.{os.getpid()}{path.suffix}")))
    return create_app(config)


def run(config: Config | None = None, workers: int = 1) -> None:
    import sys

    import uvicorn

    config = config or load_config()
    print(f"Véu {__version__} em http://{config.host}:{config.port}  (playground: /veu/playground)", file=sys.stderr)
    # Sem log de acesso: a URL pode trazer a chave da API (?key= do Gemini). A auditoria do Véu não grava valores.
    if workers > 1:
        if config.session_backend == "memoria":
            raise ConfigError("Com --workers, cada processo teria o seu cofre na memória: use sessões no Redis "
                              "(sessoes = \"redis://...\" e VEU_CHAVE_COFRE).")
        create_app(config)  # confere a configuração antes de abrir os processos
        # Cada processo monta a configuração de novo (VEU_CONFIG e VEU_*): o que veio da linha de comando vai junto.
        os.environ["VEU_HOST"], os.environ["VEU_PORTA"] = config.host, str(config.port)
        os.environ["VEU_PERFIL"] = config.profile
        uvicorn.run("veu.server.app:app_from_environment", factory=True, workers=workers, host=config.host,
                    port=config.port, log_level="info", access_log=False)
        return
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info", access_log=False)
