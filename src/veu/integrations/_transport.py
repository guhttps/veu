"""Fábrica dos transportes do Véu para o httpx e o httpx2 (que têm a mesma API, mas classes diferentes)."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

from veu.core import Veu
from veu.gateway import BlockedError, Gateway, Prepared, detect_adapter, is_streaming

_DROP_RESPONSE_HEADERS = ("content-length", "content-encoding", "transfer-encoding")


def build(http: ModuleType) -> SimpleNamespace:
    """Cria VeuTransport, AsyncVeuTransport, client() e async_client() para o módulo http dado."""

    def prepare(gateway: Gateway, request, body: bytes):
        adapter = detect_adapter(request.method, request.url.path)
        if adapter is None:
            return None, None
        query = request.url.query
        path = request.url.path + (f"?{query.decode() if isinstance(query, bytes) else query}" if query else "")
        try:
            prepared = gateway.prepare(adapter, body, path=path)
        except BlockedError as error:
            return None, http.Response(400, json=adapter.error_body(str(error)), request=request)
        except ValueError:
            return None, None
        headers = request.headers.copy()
        headers["content-length"] = str(len(prepared.body))
        headers["accept-encoding"] = "identity"
        upstream = http.Request(request.method, request.url, headers=headers, content=prepared.body,
                                extensions=request.extensions)
        return prepared, upstream

    def response_headers(response, prepared: Prepared):
        headers = response.headers.copy()
        for name in _DROP_RESPONSE_HEADERS:
            headers.pop(name, None)
        if prepared.counts:
            headers["x-veu-entidades"] = ", ".join(f"{k}={v}" for k, v in sorted(prepared.counts.items()))
        return headers

    def sync_chunks(response):
        # Respostas criadas com conteúdo pronto (como as do MockTransport) já chegam lidas.
        try:
            content = response.content
        except http.ResponseNotRead:
            yield from response.iter_raw()
        else:
            yield content

    async def async_chunks(response):
        try:
            content = response.content
        except http.ResponseNotRead:
            async for chunk in response.aiter_raw():
                yield chunk
        else:
            yield content

    class SyncTransformStream(http.SyncByteStream):
        def __init__(self, response, transformer):
            self._response = response
            self._transformer = transformer

        def __iter__(self):
            for chunk in sync_chunks(self._response):
                output = self._transformer.feed(chunk)
                if output:
                    yield output
            tail = self._transformer.close()
            if tail:
                yield tail

        def close(self):
            self._response.close()

    class AsyncTransformStream(http.AsyncByteStream):
        def __init__(self, response, transformer):
            self._response = response
            self._transformer = transformer

        async def __aiter__(self):
            async for chunk in async_chunks(self._response):
                output = self._transformer.feed(chunk)
                if output:
                    yield output
            tail = self._transformer.close()
            if tail:
                yield tail

        async def aclose(self):
            await self._response.aclose()

    class VeuTransport(http.BaseTransport):
        """Transporte síncrono: esconde os dados das requisições e restaura as respostas."""

        def __init__(self, veu: Veu | None = None, transport=None):
            self.gateway = Gateway(veu)
            self.transport = transport or http.HTTPTransport()

        def handle_request(self, request):
            prepared, upstream = prepare(self.gateway, request, request.read())
            if prepared is None:
                return upstream if upstream is not None else self.transport.handle_request(request)
            response = self.transport.handle_request(upstream)
            headers = response_headers(response, prepared)
            content_type = response.headers.get("content-type", "")
            if is_streaming(content_type):
                stream = SyncTransformStream(response, self.gateway.stream(prepared, content_type))
                return http.Response(response.status_code, headers=headers, stream=stream,
                                     extensions=response.extensions, request=request)
            try:
                body = response.read()
            finally:
                response.close()
            return http.Response(response.status_code, headers=headers,
                                 content=self.gateway.restore_body(prepared, body),
                                 extensions=response.extensions, request=request)

        def close(self):
            self.transport.close()

    class AsyncVeuTransport(http.AsyncBaseTransport):
        """Versão assíncrona do VeuTransport (AsyncOpenAI, AsyncAnthropic...)."""

        def __init__(self, veu: Veu | None = None, transport=None):
            self.gateway = Gateway(veu)
            self.transport = transport or http.AsyncHTTPTransport()

        async def handle_async_request(self, request):
            prepared, upstream = prepare(self.gateway, request, await request.aread())
            if prepared is None:
                return upstream if upstream is not None else await self.transport.handle_async_request(request)
            response = await self.transport.handle_async_request(upstream)
            headers = response_headers(response, prepared)
            content_type = response.headers.get("content-type", "")
            if is_streaming(content_type):
                stream = AsyncTransformStream(response, self.gateway.stream(prepared, content_type))
                return http.Response(response.status_code, headers=headers, stream=stream,
                                     extensions=response.extensions, request=request)
            try:
                body = await response.aread()
            finally:
                await response.aclose()
            return http.Response(response.status_code, headers=headers,
                                 content=self.gateway.restore_body(prepared, body),
                                 extensions=response.extensions, request=request)

        async def aclose(self):
            await self.transport.aclose()

    def client(veu: Veu | None = None, **kwargs):
        return http.Client(transport=VeuTransport(veu), **kwargs)

    def async_client(veu: Veu | None = None, **kwargs):
        return http.AsyncClient(transport=AsyncVeuTransport(veu), **kwargs)

    return SimpleNamespace(VeuTransport=VeuTransport, AsyncVeuTransport=AsyncVeuTransport, client=client,
                           async_client=async_client)
