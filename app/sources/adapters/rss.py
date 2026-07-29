from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from app.sources.base import SourceHealth, SourceRequest
from app.sources.models import SourceType, UnifiedDocument

Fetcher = Callable[[str], Awaitable[bytes]]


class RSSSourceAdapter:
    source_type = SourceType.RSS
    name = "rss-atom-adapter"
    version = "1.0.0"

    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def collect(self, request: SourceRequest) -> tuple[UnifiedDocument, ...]:
        payload = await self._fetcher(request.source_id)
        root = ElementTree.fromstring(payload)
        documents = _parse_feed(root, request.source_id)
        filtered = [item for item in documents if _inside_range(item.published_at, request)]
        if request.limit:
            filtered = filtered[: request.limit]
        return tuple(filtered)

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(True, self.name, self.version, "fetcher available")

    async def close(self) -> None:
        return None


def _parse_feed(root: ElementTree.Element, source_id: str) -> list[UnifiedDocument]:
    local = _local_name(root.tag)
    if local == "rss":
        nodes = root.findall("./channel/item")
    elif local == "feed":
        nodes = [node for node in root if _local_name(node.tag) == "entry"]
    else:
        raise ValueError("Unsupported RSS/Atom document")

    documents: list[UnifiedDocument] = []
    for index, node in enumerate(nodes):
        values = {_local_name(child.tag): (child.text or "").strip() for child in node}
        title = values.get("title", "")
        body = values.get("description") or values.get("summary") or values.get("content") or ""
        link = values.get("link", "")
        if not link:
            for child in node:
                if _local_name(child.tag) == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        published = values.get("pubDate") or values.get("published") or values.get("updated")
        published_at = _parse_date(published)
        document_id = values.get("guid") or values.get("id") or link or f"item-{index}"
        documents.append(
            UnifiedDocument(
                source_type=SourceType.RSS,
                source_id=source_id,
                document_id=document_id,
                title=title,
                body=body,
                published_at=published_at,
                canonical_url=link or None,
                links=(link,) if link else (),
                metadata={"feed_format": local},
            )
        )
    return documents


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _inside_range(value: datetime, request: SourceRequest) -> bool:
    if request.date_from and value < request.date_from:
        return False
    if request.date_to and value > request.date_to:
        return False
    return True


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
