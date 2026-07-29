from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from urllib.parse import urlparse

_TOKEN_RE = re.compile(r"[\wа-яё]{3,}", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DocumentSignal:
    evidence_id: str
    source_id: str
    source_type: str | None
    canonical_url: str | None
    content_hash: str | None
    fingerprint: str | None
    excerpt: str | None


@dataclass(frozen=True, slots=True)
class IndependenceCluster:
    cluster_id: str
    evidence_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_types: tuple[str, ...]
    upstream_domains: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CorroborationAssessment:
    claim_id: str
    document_count: int
    independent_cluster_count: int
    independence_score: float
    corroboration_score: float
    clusters: tuple[IndependenceCluster, ...]
    caveats: tuple[str, ...]


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    return host or None


def _tokens(text: str | None) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text or "")}


def _jaccard(left: str | None, right: str | None) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _same_story(left: DocumentSignal, right: DocumentSignal, similarity_threshold: float) -> tuple[bool, str]:
    left_domain, right_domain = _domain(left.canonical_url), _domain(right.canonical_url)
    if left.content_hash and left.content_hash == right.content_hash:
        return True, "identical_content_hash"
    if left.fingerprint and left.fingerprint == right.fingerprint:
        return True, "identical_fingerprint"
    if left_domain and right_domain and left_domain == right_domain:
        return True, "same_upstream_domain"
    if _jaccard(left.excerpt, right.excerpt) >= similarity_threshold:
        return True, "high_text_similarity"
    return False, "independent"


def assess_claim_corroboration(
    claim_id: str,
    documents: tuple[DocumentSignal, ...],
    *,
    similarity_threshold: float = 0.72,
) -> CorroborationAssessment:
    if not documents:
        return CorroborationAssessment(
            claim_id=claim_id,
            document_count=0,
            independent_cluster_count=0,
            independence_score=0.0,
            corroboration_score=0.0,
            clusters=(),
            caveats=("Нет первичных документов.",),
        )

    parent = list(range(len(documents)))
    reasons: dict[tuple[int, int], str] = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, left in enumerate(documents):
        for j in range(i + 1, len(documents)):
            same, reason = _same_story(left, documents[j], similarity_threshold)
            if same:
                union(i, j)
                reasons[(i, j)] = reason

    groups: dict[int, list[int]] = {}
    for index in range(len(documents)):
        groups.setdefault(find(index), []).append(index)

    clusters: list[IndependenceCluster] = []
    for members in groups.values():
        docs = [documents[index] for index in members]
        cluster_reasons = {
            reason for (i, j), reason in reasons.items() if i in members and j in members
        }
        reason = ",".join(sorted(cluster_reasons)) or "independent_document"
        raw = "|".join(sorted(item.evidence_id for item in docs))
        clusters.append(IndependenceCluster(
            cluster_id="cluster_" + hashlib.sha256(raw.encode()).hexdigest()[:16],
            evidence_ids=tuple(sorted(item.evidence_id for item in docs)),
            source_ids=tuple(sorted({item.source_id for item in docs})),
            source_types=tuple(sorted({item.source_type for item in docs if item.source_type})),
            upstream_domains=tuple(sorted({domain for item in docs if (domain := _domain(item.canonical_url))})),
            reason=reason,
        ))

    cluster_count = len(clusters)
    source_count = len({item.source_id for item in documents})
    type_count = len({item.source_type for item in documents if item.source_type})
    independence = min(1.0, cluster_count / max(len(documents), 1))
    diversity = min(1.0, (source_count / 3) * 0.65 + (type_count / 2) * 0.35)
    corroboration = min(1.0, (1 - math.exp(-cluster_count / 1.5)) * 0.7 + diversity * 0.3)

    caveats: list[str] = []
    if cluster_count < 2:
        caveats.append("Нет двух независимо подтверждающих кластеров.")
    if type_count < 2:
        caveats.append("Источники представлены менее чем двумя типами.")
    if cluster_count < len(documents):
        caveats.append("Часть документов определена как перепечатки или общий upstream.")

    return CorroborationAssessment(
        claim_id=claim_id,
        document_count=len(documents),
        independent_cluster_count=cluster_count,
        independence_score=round(independence, 6),
        corroboration_score=round(corroboration, 6),
        clusters=tuple(sorted(clusters, key=lambda item: item.cluster_id)),
        caveats=tuple(caveats),
    )
