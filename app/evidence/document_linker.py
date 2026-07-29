from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from app.workspace_evolution.models import WorkspaceEvolutionReport


@dataclass(slots=True, frozen=True)
class SourceDocumentEvidence:
    document_id: str
    source_id: str
    source_type: str
    source_external_id: str
    title: str
    body: str
    author: str | None
    canonical_url: str | None
    published_at: datetime
    fingerprint: str
    content_fingerprint: str


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w.-]{3,}", value.casefold(), flags=re.UNICODE)}


def _terms_for_category(report: WorkspaceEvolutionReport, category: str) -> set[str]:
    category = category.casefold()
    pairs: tuple[tuple[str, int], ...] = ()
    if "entity" in category or "entities" in category or "сущ" in category:
        pairs = report.added_entities + report.removed_entities
    elif "domain" in category or "домен" in category:
        pairs = report.added_domains + report.removed_domains
    elif "keyword" in category or "narrative" in category or "тем" in category:
        pairs = report.added_keywords + report.removed_keywords
    terms: set[str] = set()
    for name, _ in pairs:
        terms.update(_tokens(name))
    return terms


def _document_text(document: SourceDocumentEvidence) -> str:
    return f"{document.title}\n{document.body}\n{document.canonical_url or ''}".casefold()


def rank_documents_for_claim(
    report: WorkspaceEvolutionReport,
    category: str,
    statement: str,
    documents: tuple[SourceDocumentEvidence, ...],
    limit: int = 3,
) -> tuple[SourceDocumentEvidence, ...]:
    terms = _terms_for_category(report, category) | _tokens(statement)
    scored: list[tuple[float, SourceDocumentEvidence]] = []
    for document in documents:
        haystack = _document_text(document)
        hits = sum(1 for term in terms if term in haystack)
        domain_bonus = 0.0
        if document.canonical_url:
            host = (urlparse(document.canonical_url).hostname or "").casefold()
            if any(term in host for term in terms):
                domain_bonus = 2.0
        if hits == 0 and terms:
            continue
        recency = max(0.0, 1.0 - (report.current_generated_at - document.published_at).days / 365.0)
        score = hits * 2.0 + domain_bonus + recency
        scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], -item[1].published_at.timestamp(), item[1].document_id))
    return tuple(item[1] for item in scored[:limit])


def excerpt_for(document: SourceDocumentEvidence, terms: set[str], max_chars: int = 420) -> str:
    text = " ".join(document.body.split())
    lowered = text.casefold()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, min(positions) - 100) if positions else 0
    excerpt = text[start:start + max_chars]
    if start > 0:
        excerpt = "..." + excerpt
    if start + max_chars < len(text):
        excerpt += "..."
    return excerpt
