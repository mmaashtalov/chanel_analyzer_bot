"""Production owner gate and reverse proxy for the Control Center.

The public emulator and health probes remain available without credentials.
Every other route is protected with HTTP Basic authentication before traffic
reaches the Control Center. The upstream server runs only on loopback.
"""

from __future__ import annotations

import base64
import hmac
import http.client
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

HOP_BY_HOP_HEADERS: Final = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
PUBLIC_EXACT_PATHS: Final = {
    "/health",
    "/ready",
    "/emulator",
    "/favicon.ico",
    "/robots.txt",
    "/api/demo",
}
PUBLIC_PREFIXES: Final = ("/assets/", "/demo/")


def is_public_path(method: str, raw_path: str) -> bool:
    """Return whether a request may bypass the owner gate."""
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        return False
    path = urlsplit(raw_path).path
    return path in PUBLIC_EXACT_PATHS or path.startswith(PUBLIC_PREFIXES)


def _read_password() -> str:
    password_file = os.getenv("OWNER_GATE_PASSWORD_FILE", "").strip()
    if password_file:
        return Path(password_file).read_text(encoding="utf-8").strip()
    return os.getenv("OWNER_GATE_PASSWORD", "").strip()


def valid_basic_auth(header: str | None, username: str, password: str) -> bool:
    """Validate an HTTP Basic Authorization value in constant time."""
    if not header or not password:
        return False
    scheme, separator, encoded = header.partition(" ")
    if not separator or scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    supplied_user, separator, supplied_password = decoded.partition(":")
    if not separator:
        return False
    return hmac.compare_digest(supplied_user, username) and hmac.compare_digest(
        supplied_password, password
    )


def filtered_headers(headers: object, *, request: bool) -> list[tuple[str, str]]:
    """Remove hop-by-hop and sensitive proxy headers."""
    result: list[tuple[str, str]] = []
    for key, value in headers.items():  # type: ignore[attr-defined]
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
            continue
        if request and lowered in {"host", "authorization", "proxy-authorization"}:
            continue
        result.append((key, value))
    return result


class SecureProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ChannelAnalyzerOwnerGate/0.23.0"

    upstream_host = "127.0.0.1"
    upstream_port = 8766
    gate_username = "owner"
    gate_password = ""
    max_body_bytes = 2 * 1024 * 1024

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def _handle(self) -> None:
        public = is_public_path(self.command, self.path)
        if not public and not self.gate_password:
            self._plain_response(503, "Owner gate is not configured")
            return
        if not public and not valid_basic_auth(
            self.headers.get("Authorization"), self.gate_username, self.gate_password
        ):
            auth_body = b"Owner authentication required\n"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Channel Analyzer Owner"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(auth_body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(auth_body)
            return

        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if transfer_encoding and transfer_encoding != "identity":
            self._plain_response(400, "Chunked request bodies are not supported")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._plain_response(400, "Invalid Content-Length")
            return
        if content_length < 0 or content_length > self.max_body_bytes:
            self._plain_response(413, "Request body is too large")
            return
        body: bytes | None = self.rfile.read(content_length) if content_length else None

        connection = http.client.HTTPConnection(
            self.upstream_host, self.upstream_port, timeout=120
        )
        try:
            headers = dict(filtered_headers(self.headers, request=True))
            headers["Host"] = f"{self.upstream_host}:{self.upstream_port}"
            if body is not None:
                headers["Content-Length"] = str(len(body))
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = b"" if self.command == "HEAD" else response.read()
            self.send_response(response.status, response.reason)
            for key, value in filtered_headers(response.headers, request=False):
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            if response_body:
                self.wfile.write(response_body)
        except (OSError, http.client.HTTPException) as exc:
            self.log_error("upstream failure: %s", exc)
            self._plain_response(502, "Control Center is not available")
        finally:
            connection.close()

    def _plain_response(self, status: int, message: str) -> None:
        body = (message + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def wait_for_upstream(host: str, port: int, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection(host, port, timeout=3)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            response.read()
            if 200 <= response.status < 500:
                return
        except OSError as exc:
            last_error = exc
        finally:
            connection.close()
        time.sleep(1)
    raise RuntimeError(f"Control Center did not start: {last_error}")


def main() -> None:
    public_port = int(os.getenv("PORT", "8000"))
    upstream_port = int(os.getenv("UPSTREAM_PORT", "8766"))
    username = os.getenv("OWNER_GATE_USERNAME", "owner").strip() or "owner"
    password = _read_password()
    if not password:
        raise SystemExit("OWNER_GATE_PASSWORD or OWNER_GATE_PASSWORD_FILE is required")

    upstream_command = shlex.split(
        os.getenv("CONTROL_CENTER_UPSTREAM_CMD", f"{sys.executable} -m app.setup.server")
    )
    child_env = os.environ.copy()
    child_env["PORT"] = str(upstream_port)
    child_env["HOST"] = "127.0.0.1"
    child_env["CONTROL_CENTER_PORT"] = str(upstream_port)
    child_env["CONTROL_CENTER_HOST"] = "127.0.0.1"

    upstream = subprocess.Popen(upstream_command, env=child_env)
    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        wait_for_upstream("127.0.0.1", upstream_port)
        SecureProxyHandler.upstream_port = upstream_port
        SecureProxyHandler.gate_username = username
        SecureProxyHandler.gate_password = password
        SecureProxyHandler.max_body_bytes = int(
            os.getenv("OWNER_GATE_MAX_BODY_BYTES", str(2 * 1024 * 1024))
        )
        server = ThreadingHTTPServer(("0.0.0.0", public_port), SecureProxyHandler)
        server.timeout = 1
        print(
            f"Owner gate listening on 0.0.0.0:{public_port}; "
            f"Control Center upstream on 127.0.0.1:{upstream_port}",
            flush=True,
        )
        while not stop_event.is_set() and upstream.poll() is None:
            server.handle_request()
        server.server_close()
        if upstream.poll() is not None and upstream.returncode:
            raise SystemExit(upstream.returncode)
    finally:
        if upstream.poll() is None:
            upstream.terminate()
            try:
                upstream.wait(timeout=15)
            except subprocess.TimeoutExpired:
                upstream.kill()
                upstream.wait(timeout=5)


if __name__ == "__main__":
    main()
