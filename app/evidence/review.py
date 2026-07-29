from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class ClaimReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"

    @classmethod
    def parse(cls, raw: str) -> "ClaimReviewStatus":
        aliases = {
            "partial": cls.PARTIALLY_VERIFIED,
            "partially_verified": cls.PARTIALLY_VERIFIED,
            "needs_evidence": cls.NEEDS_MORE_EVIDENCE,
            "needs_more_evidence": cls.NEEDS_MORE_EVIDENCE,
        }
        normalized = raw.strip().casefold()
        if normalized in aliases:
            return aliases[normalized]
        return cls(normalized)


@dataclass(slots=True, frozen=True)
class EvidenceGap:
    claim_id: str
    category: str
    code: str
    severity: str
    description: str


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def adjusted_scores(
    confidence: float,
    evidence_quality: float,
    status: ClaimReviewStatus,
) -> tuple[float, float]:
    if status is ClaimReviewStatus.VERIFIED:
        return _bounded(confidence + 0.05), _bounded(evidence_quality + 0.05)
    if status is ClaimReviewStatus.PARTIALLY_VERIFIED:
        return _bounded(confidence * 0.95), _bounded(evidence_quality)
    if status is ClaimReviewStatus.REJECTED:
        return 0.0, _bounded(evidence_quality)
    if status is ClaimReviewStatus.NEEDS_MORE_EVIDENCE:
        return _bounded(confidence * 0.85), _bounded(evidence_quality * 0.9)
    return _bounded(confidence), _bounded(evidence_quality)


def review_completeness(claims: list[dict[str, Any]]) -> float:
    if not claims:
        return 1.0
    reviewed = sum(
        1 for claim in claims
        if claim.get("review_status", ClaimReviewStatus.UNREVIEWED.value)
        != ClaimReviewStatus.UNREVIEWED.value
    )
    return reviewed / len(claims)


def recalculate_integrity(payload: dict[str, Any]) -> str:
    canonical = {
        "subject_type": payload.get("subject_type"),
        "subject_id": payload.get("subject_id"),
        "claims": [
            {
                "claim_id": claim.get("claim_id"),
                "confidence": claim.get("confidence"),
                "evidence_quality": claim.get("evidence_quality"),
                "evidence_ids": claim.get("evidence_ids", []),
                "review_status": claim.get("review_status", "unreviewed"),
                "review_version": claim.get("review_version", 0),
                "independence_score": claim.get("independence_score", 0.0),
                "corroboration_score": claim.get("corroboration_score", 0.0),
                "claim_identity_id": claim.get("claim_identity_id"),
                "temporal_status": claim.get("temporal_status", "current"),
            }
            for claim in payload.get("claims", [])
        ],
        "evidence": sorted(
            (item.get("evidence_id"), item.get("content_hash"))
            for item in payload.get("evidence", [])
        ),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def detect_evidence_gaps(
    bundle: dict[str, Any],
    *,
    now: datetime | None = None,
    stale_after_days: int = 30,
) -> tuple[EvidenceGap, ...]:
    now = now or datetime.now(UTC)
    evidence = {item["evidence_id"]: item for item in bundle.get("evidence", [])}
    gaps: list[EvidenceGap] = []

    for claim in bundle.get("claims", []):
        claim_id = str(claim["claim_id"])
        category = str(claim.get("category", "unknown"))
        linked = [evidence[eid] for eid in claim.get("evidence_ids", []) if eid in evidence]
        primary = [item for item in linked if item.get("kind") == "primary_document"]
        source_types = {item.get("source_type") for item in primary if item.get("source_type")}

        if not primary:
            gaps.append(EvidenceGap(
                claim_id, category, "no_primary_document", "high",
                "Нет связанного первичного документа.",
            ))
        elif len(source_types) < 2:
            gaps.append(EvidenceGap(
                claim_id, category, "single_source_type", "medium",
                "Claim подтверждается первичными документами только одного типа источника.",
            ))

        corroboration = claim.get("corroboration") or {}
        independent_clusters = int(corroboration.get("independent_cluster_count", 0) or 0)
        if len(primary) >= 2 and independent_clusters and independent_clusters < 2:
            gaps.append(EvidenceGap(
                claim_id, category, "pseudo_independent_sources", "high",
                "Несколько документов относятся к одному кластеру перепечатки или общему upstream.",
            ))

        stale = False
        for item in primary:
            raw = item.get("published_at") or item.get("observed_at")
            if not raw:
                continue
            try:
                observed = datetime.fromisoformat(str(raw))
            except ValueError:
                continue
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=UTC)
            if now - observed > timedelta(days=stale_after_days):
                stale = True
        if stale:
            gaps.append(EvidenceGap(
                claim_id, category, "stale_primary_document", "medium",
                f"Есть первичный документ старше {stale_after_days} дней.",
            ))

        if float(claim.get("evidence_quality", 0.0)) < 0.7:
            gaps.append(EvidenceGap(
                claim_id, category, "low_evidence_quality", "high",
                "Evidence quality ниже 70%.",
            ))

    return tuple(gaps)
