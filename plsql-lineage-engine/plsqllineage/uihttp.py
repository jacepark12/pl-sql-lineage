"""Localhost UI HTTP for the lineage viewer (stdlib only).

Binds 127.0.0.1. Serves the engine JSON the MCP session loaded, the latest
agent-focus snapshot, SSE, and POST /invoke for driving the same tools without
stdio MCP. Not a public API: CORS is open because the browser origin is Vite
on 127.0.0.1:4173.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from plsqllineage.focus import FocusHub

if TYPE_CHECKING:
    from plsqllineage.serve import LineageSession

MAX_INVOKE_BYTES = 1 * 1024 * 1024
SSE_RETRY_MS = 2000
SSE_KEEPALIVE_S = 15.0


def parse_bind(spec: str) -> tuple[str, int]:
    """Parse ``HOST:PORT`` or ``PORT``. Rejects anything other than loopback."""
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("empty --ui bind")
    if raw.count(":") > 1:
        raise ValueError("UI HTTP binds 127.0.0.1 only")
    if ":" in raw:
        host, port_s = raw.rsplit(":", 1)
    else:
        host, port_s = "127.0.0.1", raw
    host = (host or "127.0.0.1").strip()
    if host in {"localhost", "127.0.0.1"}:
        host = "127.0.0.1"
    else:
        raise ValueError(f"UI HTTP binds 127.0.0.1 only (got {host!r})")
    try:
        port = int(port_s)
    except ValueError as exc:
        raise ValueError(f"invalid UI port: {port_s!r}") from exc
    if port < 0 or port > 65535:
        raise ValueError(f"invalid UI port: {port}")
    return host, port


def _cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-cache")


class UiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], session: LineageSession):
        self.session = session
        self.hub: FocusHub = session.hub
        self.should_stop = threading.Event()
        super().__init__(server_address, UiHandler)


class UiHandler(BaseHTTPRequestHandler):
    server: UiHTTPServer

    def log_message(self, fmt: str, *args) -> None:
        if self.path.split("?", 1)[0] == "/events":
            return
        super().log_message(fmt, *args)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send_json(200, {"ok": True, "ui": True})
            return
        if path == "/engine.json":
            self._send_engine()
            return
        if path == "/focus":
            snap = self.server.hub.snapshot()
            self._send_json(200, snap.to_json() if snap else {
                "v": 1, "tool": None, "seed": None, "columns": [], "edges": [],
                "graph": None, "seq": 0,
            })
            return
        if path == "/events":
            self._sse()
            return
        self._send_bytes(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/invoke":
            self._send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            return
        length = 0
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length > MAX_INVOKE_BYTES:
            self._send_bytes(413, b"payload too large\n", "text/plain; charset=utf-8")
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_bytes(400, b"invalid json\n", "text/plain; charset=utf-8")
            return
        if not isinstance(payload, dict):
            self._send_bytes(400, b"invalid json\n", "text/plain; charset=utf-8")
            return
        try:
            text = self.server.session.invoke(payload)
        except ValueError as exc:
            self._send_bytes(400, str(exc).encode("utf-8") + b"\n",
                             "text/plain; charset=utf-8")
            return
        self._send_bytes(200, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _send_engine(self) -> None:
        path = self.server.session.default_path
        if path is None or not Path(path).exists():
            self._send_bytes(
                404,
                b"No engine JSON. Start with --input engine.json.\n",
                "text/plain; charset=utf-8",
            )
            return
        data = Path(path).read_bytes()
        self._send_bytes(200, data, "application/json")

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        _cors(self)
        self.end_headers()
        try:
            self.wfile.write(f"retry: {SSE_RETRY_MS}\n\n".encode("utf-8"))
            self.wfile.flush()
            hub = self.server.hub
            snap = hub.snapshot()
            last_seq = 0
            if snap is not None:
                self._write_sse("focus", snap.to_json())
                last_seq = snap.seq
            while not self.server.should_stop.is_set():
                event = hub.wait_after(last_seq, SSE_KEEPALIVE_S)
                if event is not None:
                    self._write_sse("focus", event.to_json())
                    last_seq = event.seq
                else:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return

    def _write_sse(self, event: str, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        chunk = f"event: {event}\ndata: {data}\n\n".encode("utf-8")
        self.wfile.write(chunk)
        self.wfile.flush()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        _cors(self)
        self.end_headers()
        self.wfile.write(body)


def make_ui_http(session: LineageSession, host: str, port: int) -> UiHTTPServer:
    return UiHTTPServer((host, port), session)


def start_ui_thread(httpd: UiHTTPServer) -> threading.Thread:
    thread = threading.Thread(
        target=httpd.serve_forever, name="plsql-lineage-ui", daemon=True)
    thread.start()
    httpd.thread = thread  # type: ignore[attr-defined]
    return thread


def stop_ui_http(httpd: UiHTTPServer) -> None:
    httpd.should_stop.set()
    try:
        httpd.shutdown()
    except Exception:
        pass
    try:
        httpd.server_close()
    except Exception:
        pass
