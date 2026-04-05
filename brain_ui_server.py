#!/usr/bin/env python3
"""Serve the Brain Remote UI over localhost and proxy the bridge."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


HOST = "127.0.0.1"
PORT = 8000
UI_DIR = Path(r"C:\Users\gssjr\OneDrive\Desktop\CRYPTO TOOLS")
HTML_PATH = UI_DIR / "brain_remote.html"
BRIDGE_URL = "http://127.0.0.1:5000"


class BrainUIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _send_html(self, status_code: int, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _proxy_json(self, method: str, path: str, payload: dict[str, object] | None = None) -> None:
        target = f"{BRIDGE_URL}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            target,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
                try:
                    decoded = json.loads(raw.decode("utf-8"))
                except Exception:
                    decoded = {"ok": False, "error": "invalid bridge response"}
                self._send_json(response.status, decoded)
        except URLError as exc:
            self._send_json(502, {"ok": False, "error": f"bridge unreachable: {exc}"})

    def _load_bridge_json(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        target = f"{BRIDGE_URL}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            target,
            data=data,
            method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
                decoded = json.loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    return decoded
        except Exception:
            pass
        return {"ok": False}

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/brain_remote.html"}:
            try:
                html = HTML_PATH.read_text(encoding="utf-8")
                initial_state = {
                    "health": self._load_bridge_json("/health"),
                    "ask": self._load_bridge_json("/ask", {"query": "BTC"}),
                }
                injection = (
                    "<script>"
                    f"window.__INITIAL_BRAIN__ = {json.dumps(initial_state, ensure_ascii=False)};"
                    "</script>"
                )
                html = html.replace("</head>", f"{injection}</head>", 1)
                body = html.encode("utf-8")
            except Exception as exc:  # pragma: no cover - defensive
                self._send_html(
                    500,
                    f"<h1>Brain UI error</h1><pre>{exc}</pre>".encode("utf-8"),
                )
                return

            self._send_html(200, body)
            return

        if self.path == "/health":
            self._proxy_json("GET", "/health")
            return

        self._send_html(404, b"<h1>404</h1>")

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}

        if self.path in {"/ask", "/log"}:
            self._proxy_json("POST", self.path, payload)
            return

        self._send_json(404, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), BrainUIHandler)
    print(f"Serving Brain UI from {HTML_PATH}", flush=True)
    print(f"Open: http://{HOST}:{PORT}/brain_remote.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Brain UI server shutting down", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
