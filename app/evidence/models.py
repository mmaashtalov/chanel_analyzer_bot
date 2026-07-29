from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EvidenceKind(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"
    SNAPSHOT = "snapshot"
    COMPUTATION = "computation"
    ENTITY_MENTION = "entity_mention"
    ALERT = "alert"


class EvidenceStrength(StrEnum):
    DIRECT = "direct"
    CORROBORATING = "corroborating"
    CONTEXTUAL = "contextual"


@dataclass(slots=True, frozen=True)
class EvidenceReference:
    evidence_id: str
    kind: EvidenceKind
    source_id: str
    locator: str
    label: str
    strength: EvidenceStrength
    observed_at: datetime | None = None
    value: Any = None
    content_hash: str | None = None
    document_id: str | None = None
    source_type: str | None = None
    canonical_url: str | None = None
    author: str | None = None
    excerpt: str | None = None
    published_at: datetime | None = None
    fingerprint: str | None = None


@dataclass(slots=True, frozen=True)
class AnalyticClaim:
    claim_id: str
    claim_index: int
    category: str
    statement: str
    assessment: str
    severity: str
    confidence: float
    evidence_ids: tuple[str, ...]
    evidence_quality: float
    caveats: tuple[str, ...] = ()
    review_status: str = "unreviewed"
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    review_version: int = 0
    claim_identity_id: str | None = None
    temporal_status: str = "current"


@dataclass(slots=True, frozen=True)
class ProvenanceBundle:
    bundle_id: str
    subject_type: str
    subject_id: str
    methodology_version: str
    generated_at: datetime
    claims: tuple[AnalyticClaim, ...]
    evidence: tuple[EvidenceReference, ...]
    completeness: float
    integrity_hash: str
    limitations: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        for claim in payload["claims"]:
            if claim.get("reviewed_at") is not None:
                claim["reviewed_at"] = claim["reviewed_at"].isoformat()
        for item in payload["evidence"]:
            item["kind"] = item["kind"].value if hasattr(item["kind"], "value") else item["kind"]
            item["strength"] = item["strength"].value if hasattr(item["strength"], "value") else item["strength"]
            if item["observed_at"] is not None:
                item["observed_at"] = item["observed_at"].isoformat()
            if item["published_at"] is not None:
                item["published_at"] = item["published_at"].isoformat()
        return payload
