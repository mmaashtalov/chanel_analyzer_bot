from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit


class SourceType(StrEnum):
    TELEGRAM = "telegram"
    RSS = "rss"
    WEB = "web"
    NEWS = "news"


@dataclass(slots=True, frozen=True)
class Attachment:
    kind: str
    url: str | None = None
    mime_type: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class UnifiedDocument:
    source_type: SourceType
    source_id: str
    document_id: str
    body: str
    published_at: datetime
    title: str = ""
    language: str | None = None
    author: str | None = None
    canonical_url: str | None = None
    links: tuple[str, ...] = ()
    hashtags: tuple[str, ...] = ()
    mentions: tuple[str, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            object.__setattr__(self, "published_at", self.published_at.replace(tzinfo=UTC))
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.document_id.strip():
            raise ValueError("document_id is required")

    @property
    def fingerprint(self) -> str:
        payload = {
            "source_type": self.source_type.value,
            "source_id": self.source_id.strip().lower(),
            "document_id": self.document_id.strip(),
            "published_at": self.published_at.astimezone(UTC).isoformat(timespec="seconds"),
            "title": _normalize_text(self.title),
            "body": _normalize_text(self.body),
            "links": sorted(_canonicalize_url(url) for url in self.links),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def content_fingerprint(self) -> str:
        """Cross-source fingerprint that intentionally excludes source identity."""
        payload = {
            "title": _normalize_text(self.title),
            "body": _normalize_text(self.body),
            "links": sorted(_canonicalize_url(url) for url in self.links),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "document_id": self.document_id,
            "title": self.title,
            "body": self.body,
            "language": self.language,
            "published_at": self.published_at.isoformat(),
            "author": self.author,
            "canonical_url": self.canonical_url,
            "links": list(self.links),
            "hashtags": list(self.hashtags),
            "mentions": list(self.mentions),
            "attachments": [
                {"kind": item.kind, "url": item.url, "mime_type": item.mime_type, "metadata": item.metadata}
                for item in self.attachments
            ],
            "metadata": self.metadata,
            "fingerprint": self.fingerprint,
            "content_fingerprint": self.content_fingerprint,
        }


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonicalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        scheme = parts.scheme.lower() or "https"
        host = (parts.hostname or "").lower()
        port = parts.port
        netloc = host if port is None else f"{host}:{port}"
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, parts.query, ""))
    except ValueError:
        return value.strip()
