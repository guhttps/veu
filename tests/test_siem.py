"""Auditoria no SIEM: syslog (RFC 5424 por UDP e TCP), Splunk HEC e a fila que nunca segura as requisições."""

import asyncio
import json
import socket
import threading

import httpx
import pytest

from veu.config import Config, ConfigError, load_config
from veu.server import create_app
from veu.server.siem import HecSender, SiemForwarder, SyslogSender, syslog_message

BOM = b"\xef\xbb\xbf"


def parse(message: bytes) -> tuple[str, dict]:
    header, _, body = message.partition(BOM)
    return header.decode(), json.loads(body)


def test_syslog_message_follows_rfc5424():
    record = {"quando": "2026-11-08T03:00:00.000+00:00", "provedor": "openai", "entidades": {"CPF": 1}, "hash": "ab"}
    header, body = parse(syslog_message(record, "gateway-1"))
    assert header.startswith("<110>1 2026-11-08T03:00:00.000+00:00 gateway-1 veu ")  # log audit, informativo
    assert header.endswith(" requisicao - ")
    assert body == record
    assert syslog_message({**record, "bloqueado": ["CPF"]}, "h").startswith(b"<108>")  # aviso
    assert syslog_message({**record, "status": 502}, "h").startswith(b"<107>")         # erro
    assert b" desviado - " in syslog_message({**record, "desviado_para": "interno"}, "h")


def test_syslog_over_udp():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(5)
    sender = SyslogSender(f"udp://127.0.0.1:{server.getsockname()[1]}")
    sender.send([{"provedor": "a"}, {"provedor": "b"}])
    received = [parse(server.recv(65535))[1]["provedor"] for _ in range(2)]
    assert received == ["a", "b"]
    sender.close()
    server.close()


def test_syslog_over_tcp_uses_octet_counting():
    server = socket.create_server(("127.0.0.1", 0))
    chunks = []

    def accept():
        connection, _ = server.accept()
        with connection:
            while data := connection.recv(65535):
                chunks.append(data)

    thread = threading.Thread(target=accept)
    thread.start()
    sender = SyslogSender(f"tcp://127.0.0.1:{server.getsockname()[1]}")
    sender.send([{"provedor": "a"}, {"provedor": "ç"}])
    sender.close()
    thread.join(5)
    server.close()
    data, frames = b"".join(chunks), []
    while data:
        size, _, rest = data.partition(b" ")
        frames.append(rest[:int(size)])
        data = rest[int(size):]
    assert [parse(frame)[1]["provedor"] for frame in frames] == ["a", "ç"]


def test_hec_batches_events_with_the_token():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "Success", "code": 0})

    sender = HecSender("https://splunk.example:8088/services/collector/event", "tok-123",
                       transport=httpx.MockTransport(handler))
    sender.send([{"quando": "2026-11-08T03:00:00+00:00", "provedor": "a"}, {"provedor": "b"}])
    (request,) = requests
    assert request.headers["authorization"] == "Splunk tok-123"
    events = [json.loads(line) for line in request.content.decode().replace("}{", "}\n{").splitlines()]
    assert [event["event"]["provedor"] for event in events] == ["a", "b"]
    assert events[0]["sourcetype"] == "veu:auditoria" and events[0]["time"] == 1794106800.0
    sender.client.close()


def test_hec_error_status_raises():
    sender = HecSender("https://splunk.example/x", "t", transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(OSError, match="403"):
        sender.send([{"a": 1}])


class Recorder:
    def __init__(self, fail_times=0):
        self.batches, self.fail_times = [], fail_times

    def send(self, records):
        if self.fail_times:
            self.fail_times -= 1
            raise OSError("fora do ar")
        self.batches.append(list(records))


def test_forwarder_retries_once_then_counts_failures():
    flaky, broken = Recorder(fail_times=1), Recorder(fail_times=99)
    forwarder = SiemForwarder([flaky, broken], sleep=lambda seconds: None)
    for n in range(3):
        forwarder.submit({"n": n})
    assert forwarder.flush()
    assert [record["n"] for batch in flaky.batches for record in batch] == [0, 1, 2]
    assert forwarder.failures == 3 and forwarder.sent == 3  # o quebrado perdeu as 3; o instável entregou depois
    forwarder.close()


def test_forwarder_drops_when_the_queue_is_full():
    gate = threading.Event()

    class Slow:
        def send(self, records):
            gate.wait(5)

    forwarder = SiemForwarder([Slow()], max_queue=2, batch=1)
    for n in range(10):
        forwarder.submit({"n": n})
    assert forwarder.dropped >= 7  # submit nunca espera: o excedente é descartado e contado
    gate.set()
    forwarder.close()


def test_close_does_not_hang_when_the_siem_is_down_and_the_queue_is_full():
    import time

    gate, entered = threading.Event(), threading.Event()

    class Stuck:
        def send(self, records):
            entered.set()
            gate.wait(10)

    forwarder = SiemForwarder([Stuck()], max_queue=2, batch=1)
    forwarder.submit({"n": 0})
    assert entered.wait(5)  # a thread está presa no envio...
    for n in range(1, 5):
        forwarder.submit({"n": n})  # ...e a fila, cheia
    started = time.monotonic()
    forwarder.close(timeout=0.3)
    assert time.monotonic() - started < 2
    gate.set()


def test_config_validation(monkeypatch, tmp_path):
    with pytest.raises(ConfigError, match="udp://"):
        Config(siem_syslog="http://siem:514")
    with pytest.raises(ConfigError, match="hec_token_env"):
        Config(siem_hec_url="https://splunk:8088/services/collector/event")
    monkeypatch.setenv("TOKEN_HEC", "abc")
    path = tmp_path / "veu.toml"
    path.write_text('[siem]\nsyslog = "tls://siem:6514"\nhec_url = "https://splunk:8088/x"\nhec_token_env = "TOKEN_HEC"\n',
                    encoding="utf-8")
    config = load_config(str(path))
    assert (config.siem_syslog, config.siem_hec_url, config.siem_hec_token) == ("tls://siem:6514", "https://splunk:8088/x", "abc")


def test_gateway_sends_each_audit_line_to_syslog(tmp_path):
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(5)
    audit = tmp_path / "auditoria.jsonl"
    upstream = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"choices": [{"index": 0, "message": {"content": "ok [CPF_1]"}}]}))
    app = create_app(Config(audit_log=str(audit), siem_syslog=f"udp://127.0.0.1:{server.getsockname()[1]}"),
                     upstream_transport=upstream)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            await c.post("/v1/chat/completions", headers={"authorization": "Bearer x"},
                         json={"model": "m", "messages": [{"role": "user", "content": "CPF 529.982.247-25"}]})
            return (await c.get("/veu/metricas")).text

    metrics = asyncio.run(run())
    assert app.state.siem.flush()
    _, sent = parse(server.recv(65535))
    line = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert sent == line and sent["hash"]           # a mesma linha, com o hash da cadeia
    assert "529.982.247-25" not in json.dumps(sent)  # só metadados
    assert "veu_siem_enviados_total" in metrics
    server.close()
