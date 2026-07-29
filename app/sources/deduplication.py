from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.sources.models import UnifiedDocument


@dataclass(slots=True, frozen=True)
class DuplicateGroup:
    content_fingerprint: str
    documents: tuple[UnifiedDocument, ...]

    @property
    def first_seen(self) -> datetime:
        return min(item.published_at for item in self.documents)


def deduplicate_exact(documents: tuple[UnifiedDocument, ...]) -> tuple[UnifiedDocument, ...]:
    seen: set[str] = set()
    result: list[UnifiedDocument] = []
    for document in documents:
        if document.fingerprint in seen:
            continue
        seen.add(document.fingerprint)
        result.append(document)
    return tuple(result)


def group_cross_source_duplicates(documents: tuple[UnifiedDocument, ...]) -> tuple[DuplicateGroup, ...]:
    grouped: dict[str, list[UnifiedDocument]] = {}
    for document in documents:
        grouped.setdefault(document.content_fingerprint, []).append(document)
    groups = [
        DuplicateGroup(fingerprint, tuple(sorted(items, key=lambda item: item.published_at)))
        for fingerprint, items in grouped.items()
        if len({item.source_type for item in items}) > 1
    ]
    return tuple(sorted(groups, key=lambda item: item.first_seen))
