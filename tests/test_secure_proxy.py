from __future__ import annotations

import base64
from email.message import Message

from app.setup.secure_proxy import filtered_headers, is_public_path, valid_basic_auth


def basic(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_public_routes_are_read_only() -> None:
    assert is_public_path("GET", "/health")
    assert is_public_path("HEAD", "/emulator?step=2")
    assert is_public_path("GET", "/assets/app.css")
    assert not is_public_path("POST", "/api/demo")
    assert not is_public_path("GET", "/")
    assert not is_public_path("GET", "/api/status")


def test_basic_auth_is_strict() -> None:
    assert valid_basic_auth(basic("owner", "correct"), "owner", "correct")
    assert not valid_basic_auth(basic("owner", "wrong"), "owner", "correct")
    assert not valid_basic_auth(basic("other", "correct"), "owner", "correct")
    assert not valid_basic_auth("Bearer token", "owner", "correct")
    assert not valid_basic_auth("Basic !!!", "owner", "correct")
    assert not valid_basic_auth(None, "owner", "correct")
    assert not valid_basic_auth(basic("owner", "correct"), "owner", "")


def test_proxy_headers_remove_hop_by_hop_and_authorization() -> None:
    headers = Message()
    headers["Host"] = "public.example"
    headers["Authorization"] = "Basic secret"
    headers["Connection"] = "keep-alive"
    headers["Content-Length"] = "12"
    headers["Content-Type"] = "application/json"
    headers["X-Request-ID"] = "abc"

    forwarded = dict(filtered_headers(headers, request=True))
    assert "Host" not in forwarded
    assert "Authorization" not in forwarded
    assert "Connection" not in forwarded
    assert "Content-Length" not in forwarded
    assert forwarded["Content-Type"] == "application/json"
    assert forwarded["X-Request-ID"] == "abc"
