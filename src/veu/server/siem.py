"""Envio da auditoria para um SIEM: syslog (RFC 5424) e Splunk HTTP Event Collector (HEC).

    [siem]
    syslog = "tls://siem.interna:6514"          # udp://, tcp:// ou tls://
    hec_url = "https://splunk.interna:8088/services/collector/event"
    hec_token_env = "VEU_HEC_TOKEN"

Cada linha da auditoria (só metadados, nunca os valores, com o hash encadeado) vai também para o SIEM, numa
thread separada: um SIEM lento ou fora do ar nunca atrasa nem derruba as requisições. Se a fila encher, as linhas
mais novas são descartadas e contadas (veu_siem_descartados_total); o arquivo de auditoria continua com tudo.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from urllib.parse import urlsplit

logger = logging.getLogger("veu.siem")

FACILITY_AUDIT = 13  # "log audit", RFC 5424
SYSLOG_SCHEMES = ("udp", "tcp", "tls")


def _severity(record: dict) -> int:
    status = record.get("status") or 200
    if isinstance(status, int) and status >= 500:
        return 3  # erro
    if record.get("bloqueado"):
        return 4  # aviso
    return 6  # informativo


def _message_id(record: dict) -> str:
    if record.get("bloqueado"):
        return "bloqueado"
    if record.get("desviado_para"):
        return "desviado"
    return "requisicao"


def _hostname() -> str:
    name = "".join(char for char in socket.gethostname() if 33 <= ord(char) <= 126)
    return name[:255] or "-"


def syslog_message(record: dict, hostname: str | None = None, app: str = "veu") -> bytes:
    """Uma linha da auditoria no formato RFC 5424, com o JSON da linha como mensagem."""
    priority = FACILITY_AUDIT * 8 + _severity(record)
    timestamp = record.get("quando") or datetime.now(UTC).isoformat(timespec="milliseconds")
    header = f"<{priority}>1 {timestamp} {hostname or _hostname()} {app} {os.getpid()} {_message_id(record)} - "
    body = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    return header.encode("ascii", "replace") + b"\xef\xbb\xbf" + body.encode("utf-8")  # BOM: a mensagem é UTF-8


def parse_syslog_url(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in SYSLOG_SCHEMES or not parts.hostname:
        raise ValueError(f'siem syslog: use udp://, tcp:// ou tls:// com servidor e porta (recebi "{url}").')
    default_port = {"udp": 514, "tcp": 601, "tls": 6514}[parts.scheme]
    return parts.scheme, parts.hostname, parts.port or default_port


class SyslogSender:
    """Syslog por UDP (um datagrama por linha) ou por TCP/TLS (enquadramento por contagem de octetos, RFC 6587)."""

    def __init__(self, url: str, timeout: float = 5.0, context: ssl.SSLContext | None = None):
        self.scheme, self.host, self.port = parse_syslog_url(url)
        self.timeout = timeout
        self.context = context or ssl.create_default_context()
        self._socket: socket.socket | None = None
        self._hostname = _hostname()

    def _connect(self) -> socket.socket:
        if self._socket is None:
            if self.scheme == "udp":
                self._socket = socket.socket(socket.AF_INET6 if ":" in self.host else socket.AF_INET, socket.SOCK_DGRAM)
            else:
                raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
                self._socket = self.context.wrap_socket(raw, server_hostname=self.host) if self.scheme == "tls" else raw
        return self._socket

    def send(self, records: list[dict]) -> None:
        messages = [syslog_message(record, self._hostname) for record in records]
        try:
            sock = self._connect()
            if self.scheme == "udp":
                for message in messages:
                    sock.sendto(message, (self.host, self.port))
            else:
                sock.sendall(b"".join(str(len(message)).encode() + b" " + message for message in messages))
        except OSError:
            self.close()  # a próxima tentativa reconecta
            raise

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None


class HecSender:
    """Splunk HTTP Event Collector: os eventos de um lote vão num POST só."""

    def __init__(self, url: str, token: str, timeout: float = 5.0, transport=None, verify: bool = True):
        import httpx

        if not token:
            raise ValueError("siem hec: defina o token (hec_token_env).")
        self.url = url
        self.client = httpx.Client(timeout=timeout, transport=transport, verify=verify,
                                   headers={"authorization": f"Splunk {token}"})
        self._hostname = _hostname()

    def send(self, records: list[dict]) -> None:
        body = "".join(json.dumps(self._event(record), ensure_ascii=False, separators=(",", ":")) for record in records)
        response = self.client.post(self.url, content=body.encode("utf-8"), headers={"content-type": "application/json"})
        if response.status_code >= 300:
            raise OSError(f"HEC respondeu {response.status_code}")

    def _event(self, record: dict) -> dict:
        try:
            when = datetime.fromisoformat(record["quando"]).timestamp()
        except (KeyError, TypeError, ValueError):
            when = time.time()
        return {"time": round(when, 3), "host": self._hostname, "source": "veu", "sourcetype": "veu:auditoria",
                "event": record}

    def close(self) -> None:
        self.client.close()


class SiemForwarder:
    """Fila e thread de envio: quem chama submit() nunca espera pelo SIEM."""

    def __init__(self, senders: Iterable, max_queue: int = 10_000, batch: int = 100, retry_delay: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.senders = list(senders)
        self.batch = batch
        self.retry_delay = retry_delay
        self._sleep = sleep
        self._queue: queue.Queue = queue.Queue(max_queue)
        self.sent = 0
        self.failures = 0
        self.dropped = 0
        self._last_warning = 0.0
        self._thread = threading.Thread(target=self._run, name="veu-siem", daemon=True)
        self._thread.start()

    def submit(self, record: dict) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while True:
            first = self._queue.get()
            if first is None:
                return
            records, stop = [first], False
            while len(records) < self.batch:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is None:
                    stop = True
                    break
                records.append(item)
            self._deliver(records)
            for _ in records:
                self._queue.task_done()
            if stop:
                return

    def _deliver(self, records: list[dict]) -> None:
        for sender in self.senders:
            for attempt in range(2):  # uma nova tentativa depois de uma pausa curta; depois, desiste do lote
                try:
                    sender.send(records)
                    self.sent += len(records)
                    break
                except Exception as exc:  # noqa: BLE001 - o envio ao SIEM nunca pode derrubar o Véu
                    if attempt == 0:
                        self._sleep(self.retry_delay)
                        continue
                    self.failures += len(records)
                    now = time.monotonic()
                    if now - self._last_warning > 60:
                        self._last_warning = now
                        logger.warning("Não consegui enviar a auditoria ao SIEM (%s): %s", type(sender).__name__, exc)

    def flush(self, timeout: float = 5.0) -> bool:
        """Espera a fila esvaziar (para testes e para o encerramento)."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.01)
        return True

    def close(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        self._thread.join(timeout)
        for sender in self.senders:
            close = getattr(sender, "close", None)
            if close:
                close()


def forwarder_from_config(config) -> SiemForwarder | None:
    senders: list = []
    if config.siem_syslog:
        senders.append(SyslogSender(config.siem_syslog))
    if config.siem_hec_url:
        senders.append(HecSender(config.siem_hec_url, config.siem_hec_token or ""))
    return SiemForwarder(senders) if senders else None
