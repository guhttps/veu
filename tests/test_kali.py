"""Achados dos ataques feitos de uma máquina virtual Kali (o NAT do VirtualBox leva o 10.0.2.2 ao 127.0.0.1)."""

import http.client
import socket
import threading
import time

import pytest

pytest.importorskip("uvicorn")

import uvicorn  # noqa: E402

from veu.config import Config, ConfigError, TeamConfig  # noqa: E402
from veu.server import (
    create_app,  # noqa: E402
    protocol,  # noqa: E402
)


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.setattr(protocol, "HEADER_TIMEOUT", 0.5)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(Config()), host="127.0.0.1", port=port, log_level="error",
                                           server_header=False, http=protocol.GuardedH11Protocol))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(5)


def _closed_within(sock: socket.socket, seconds: float) -> bool:
    sock.settimeout(seconds)
    try:
        return sock.recv(100) == b""
    except (TimeoutError, ConnectionResetError):
        return False


def test_half_sent_header_is_closed(live_server):
    """Slowloris: o cabeçalho pela metade não segura a conexão para sempre."""
    with socket.create_connection(("127.0.0.1", live_server)) as sock:
        sock.sendall(b"GET /veu/saude HTTP/1.1\r\nHost: 127.0.0.1\r\nX-a: ")
        assert _closed_within(sock, 3)


def test_complete_requests_and_keep_alive_still_work(live_server):
    connection = http.client.HTTPConnection("127.0.0.1", live_server, timeout=3)
    for _ in range(2):  # a mesma conexão, mais devagar que o limite: só o cabeçalho pela metade conta
        connection.request("GET", "/veu/saude")
        response = connection.getresponse()
        assert response.status == 200 and response.getheader("server") is None
        response.read()
        time.sleep(0.8)
    # Depois dos pedidos completos, um seguinte pela metade também é fechado.
    connection.sock.sendall(b"GET /veu/saude HTTP/1.1\r\nHost: 127")
    assert _closed_within(connection.sock, 3)
    connection.close()


def test_proxied_html_cannot_run_scripts_on_the_veu_origin():
    """O provedor responde na origem do Véu (a do painel): HTML vindo dele fica numa sandbox, sem script."""
    import httpx
    from test_server import call

    def upstream(request):
        return httpx.Response(200, html="<script>fetch('/veu/painel/estado')</script>",
                              headers={"content-security-policy": "default-src *", "x-content-type-options": "x"})

    app = create_app(Config(), upstream_transport=httpx.MockTransport(upstream))
    response = call(app, "GET", "/qualquer/coisa")
    assert response.headers["content-security-policy"].startswith("sandbox")
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("options", [
    {"token": "123456"},
    {"token": "x" * 19},
    {"token": "x" * 40, "teams": {"rh": TeamConfig("rh", "rh-2026")}},
])
def test_exposed_server_refuses_short_tokens(options):
    """Fora do localhost, sem limite de tentativas, um token curto pode ser adivinhado."""
    with pytest.raises(ConfigError, match="20"):
        create_app(Config(host="0.0.0.0", **options))


def test_short_token_is_still_fine_on_localhost():
    create_app(Config(token="curto"))
    create_app(Config(host="0.0.0.0", token="x" * 20))


def test_every_response_has_nosniff_and_no_referrer():
    """nikto no modo exposto: os erros JSON (401, 404) também saem com os cabeçalhos de segurança."""
    import httpx
    from test_server import Upstream, call

    app = create_app(Config(), upstream_transport=httpx.MockTransport(Upstream()))
    for method, path in (("GET", "/veu/saude"), ("POST", "/veu/v1/detectar"), ("GET", "/veu/nao-existe")):
        response = call(app, method, path, json={"texto": "x"} if method == "POST" else None)
        assert response.headers["x-content-type-options"] == "nosniff", path
        assert response.headers["referrer-policy"] == "no-referrer", path
