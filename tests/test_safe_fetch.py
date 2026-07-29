from __future__ import annotations

import socket

import pytest

from app.sources.http import UnsafeSourceURL, _validate_url


def test_safe_fetch_rejects_non_http_scheme():
    with pytest.raises(UnsafeSourceURL):
        _validate_url("file:///etc/passwd")


def test_safe_fetch_rejects_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, 0, 0, "", ("127.0.0.1", 443))])
    with pytest.raises(UnsafeSourceURL):
        _validate_url("https://example.org/feed")


def test_safe_fetch_allows_public_address(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, 0, 0, "", ("93.184.216.34", 443))])
    _validate_url("https://example.org/feed")
