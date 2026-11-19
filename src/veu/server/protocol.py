"""Protocolo HTTP do servidor: fecha conexões que não terminam de mandar o cabeçalho (slowloris).

O uvicorn só marca tempo entre um pedido e outro: uma conexão que manda o cabeçalho pela metade e para fica aberta
para sempre. Um programa na mesma máquina (ou numa máquina virtual que alcança o 127.0.0.1) poderia abrir milhares
delas. Aqui, quem não termina o cabeçalho em HEADER_TIMEOUT segundos é desconectado.
"""

from __future__ import annotations

import asyncio

import h11
from uvicorn.protocols.http.h11_impl import H11Protocol

HEADER_TIMEOUT = 15.0


class GuardedH11Protocol(H11Protocol):
    _header_timer: asyncio.TimerHandle | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        super().connection_made(transport)
        self._watch_header()

    def data_received(self, data: bytes) -> None:
        super().data_received(data)
        if self.conn.their_state is h11.IDLE:
            self._watch_header()  # um pedido novo começou a chegar (ou nem começou)
        else:
            self._stop_watching()

    def connection_lost(self, exc: Exception | None) -> None:
        self._stop_watching()
        super().connection_lost(exc)

    def _watch_header(self) -> None:
        if self._header_timer is None and not self.transport.is_closing():
            self._header_timer = self.loop.call_later(HEADER_TIMEOUT, self._header_timeout)

    def _stop_watching(self) -> None:
        if self._header_timer is not None:
            self._header_timer.cancel()
            self._header_timer = None

    def _header_timeout(self) -> None:
        self._header_timer = None
        if self.conn.their_state is h11.IDLE and not self.transport.is_closing():
            self.transport.close()
