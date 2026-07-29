from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class ClaimRelationType(StrEnum):
    SUPPORTS = "supports"
    UPDATES = "updates"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"


class TemporalClaimStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class ClaimSnapshot:
    claim_id: str
    category: str
    statement: str
    assessment: str
    generated_at: str
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class TemporalRelation:
    relation_type: ClaimRelationType
    confidence: float
    rationale: tuple[str, ...]


_STOPWORDS = {
    "и", "в", "на", "с", "по", "к", "из", "для", "что", "это", "как", "а", "но",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "are",
}
_NEGATIONS = {"не", "нет", "отсутствует", "прекращен", "снижение", "уменьшилось", "падение", "not", "no", "decrease", "decline"}
_POSITIVE_CHANGE = {"рост", "увеличилось", "повышение", "запуск", "начало", "increase", "growth", "launched"}
_NEGATIVE_CHANGE = {"снижение", "уменьшилось", "падение", "прекращение", "отмена", "decrease", "decline", "cancelled"}


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[\wа-яё-]+", text.casefold())
        if len(token) > 2 and token not in _STOPWORDS
    }


def stable_claim_identity(category: str, statement: str) -> str:
    tokens = sorted(_tokens(statement))
    # Numbers are deliberately excluded from the identity so value updates stay on one timeline.
    directional = _NEGATIONS | _POSITIVE_CHANGE | _NEGATIVE_CHANGE
    semantic = [
        token for token in tokens
        if not token.replace(".", "", 1).isdigit() and token not in directional
    ]
    raw = f"{category.casefold()}|{'|'.join(semantic[:24])}"
    return "cid_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def text_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _numbers(text: str) -> tuple[float, ...]:
    values: list[float] = []
    for raw in re.findall(r"-?\d+(?:[.,]\d+)?", text):
        try:
            values.append(float(raw.replace(",", ".")))
        except ValueError:
            pass
    return tuple(values)


def classify_relation(previous: ClaimSnapshot, current: ClaimSnapshot) -> TemporalRelation:
    similarity = text_similarity(previous.statement, current.statement)
    previous_tokens = _tokens(previous.statement + " " + previous.assessment)
    current_tokens = _tokens(current.statement + " " + current.assessment)
    rationale: list[str] = [f"text_similarity={similarity:.3f}"]

    negation_flip = bool(previous_tokens & _NEGATIONS) != bool(current_tokens & _NEGATIONS)
    direction_flip = (
        bool(previous_tokens & _POSITIVE_CHANGE) and bool(current_tokens & _NEGATIVE_CHANGE)
    ) or (
        bool(previous_tokens & _NEGATIVE_CHANGE) and bool(current_tokens & _POSITIVE_CHANGE)
    )
    if negation_flip or direction_flip:
        rationale.append("semantic_direction_changed")
        return TemporalRelation(ClaimRelationType.CONTRADICTS, max(0.65, similarity), tuple(rationale))

    previous_numbers, current_numbers = _numbers(previous.statement), _numbers(current.statement)
    if similarity >= 0.5 and previous_numbers and current_numbers and previous_numbers != current_numbers:
        rationale.append("numeric_value_changed")
        return TemporalRelation(ClaimRelationType.UPDATES, min(0.95, 0.65 + similarity * 0.3), tuple(rationale))

    if similarity >= 0.78:
        rationale.append("same_assertion_reobserved")
        return TemporalRelation(ClaimRelationType.SUPPORTS, min(0.98, 0.7 + similarity * 0.28), tuple(rationale))

    if similarity >= 0.42:
        rationale.append("newer_claim_replaces_previous_scope")
        return TemporalRelation(ClaimRelationType.SUPERSEDES, min(0.9, 0.55 + similarity * 0.35), tuple(rationale))

    # Claims sharing an explicit identity but with substantial wording drift are conservatively updates.
    rationale.append("same_identity_with_material_wording_change")
    return TemporalRelation(ClaimRelationType.UPDATES, 0.55, tuple(rationale))


def timeline_integrity(claim_ids: Iterable[str], relations: Iterable[tuple[str, str, str]]) -> str:
    payload = "|".join(sorted(claim_ids)) + "||" + "|".join(
        sorted(f"{source}>{kind}>{target}" for source, target, kind in relations)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
