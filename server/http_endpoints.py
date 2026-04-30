from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from typing import Any


class ServerHTTPProbe:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        metrics_text: Callable[[], str],
        health: Callable[[], dict[str, Any]],
        ready: Callable[[], dict[str, Any]],
    ) -> None:
        self.host = host
        self.port = port
        self.metrics_text = metrics_text
        self.health = health
        self.ready = ready
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def stop(self) -> None:
        if not self._server:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
            request_line = raw.decode("ascii", errors="replace").strip()
            parts = request_line.split()
            path = parts[1] if len(parts) >= 2 else "/"
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                if not line or line in (b"\r\n", b"\n"):
                    break
            if path == "/metrics":
                await self._write(writer, 200, self.metrics_text(), "text/plain; version=0.0.4; charset=utf-8")
            elif path == "/health":
                await self._write_json(writer, 200, self.health())
            elif path == "/ready":
                payload = self.ready()
                await self._write_json(writer, 200 if payload.get("ready") else 503, payload)
            else:
                await self._write_json(writer, 404, {"ok": False, "error": "not_found"})
        except (asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def _write_json(self, writer: asyncio.StreamWriter, status: int, payload: dict[str, Any]) -> None:
        await self._write(writer, status, json.dumps(payload, separators=(",", ":"), ensure_ascii=False), "application/json; charset=utf-8")

    async def _write(self, writer: asyncio.StreamWriter, status: int, body: str, content_type: str) -> None:
        reason = "OK" if status == 200 else "Service Unavailable" if status == 503 else "Not Found"
        payload = body.encode("utf-8")
        header = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(header + payload)
        await writer.drain()
