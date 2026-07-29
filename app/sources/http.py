from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class UnsafeSourceURL(ValueError):
    pass


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeSourceURL("Разрешены только http/https URL")
    if not parsed.hostname:
        raise UnsafeSourceURL("URL не содержит hostname")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise UnsafeSourceURL("Hostname не разрешается") from exc
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if (address.is_private or address.is_loopback or address.is_link_local or
                address.is_multicast or address.is_reserved or address.is_unspecified):
            raise UnsafeSourceURL("Локальные и служебные адреса запрещены")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved = urljoin(req.full_url, newurl)
        _validate_url(resolved)
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def _fetch(url: str, timeout: int, max_bytes: int) -> bytes:
    _validate_url(url)
    request = Request(url, headers={"User-Agent": "TelegramIntelligencePlatform/0.19"})
    opener = build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("RSS payload превышает допустимый размер")
    return payload


async def safe_fetch(url: str, *, timeout: int = 30, max_bytes: int = 5_000_000) -> bytes:
    return await asyncio.to_thread(_fetch, url, timeout, max_bytes)
