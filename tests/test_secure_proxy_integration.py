from __future__ import annotations

import base64
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from app.setup.secure_proxy import SecureProxyHandler


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = f"upstream:{self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def request(port: int, path: str, authorization: str | None = None) -> tuple[int, bytes]:
    headers = {"Authorization": authorization} if authorization else {}
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_secure_proxy_enforces_owner_gate_over_http() -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    SecureProxyHandler.upstream_port = upstream.server_address[1]
    SecureProxyHandler.gate_username = "owner"
    SecureProxyHandler.gate_password = "correct-password"
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), SecureProxyHandler)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()

    try:
        proxy_port = proxy.server_address[1]
        status, body = request(proxy_port, "/health")
        assert status == 200
        assert body == b"upstream:/health"

        status, _ = request(proxy_port, "/")
        assert status == 401

        token = base64.b64encode(b"owner:correct-password").decode()
        status, body = request(proxy_port, "/", f"Basic {token}")
        assert status == 200
        assert body == b"upstream:/"
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()
        proxy_thread.join(timeout=5)
        upstream_thread.join(timeout=5)
