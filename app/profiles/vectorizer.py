from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from statistics import mean

from app.domain.models import ChannelSnapshot
from app.profiling.models import ContentDNAProfile
from app.profiles.models import IntelligenceProfile

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{3,}")
VECTOR_DIM = 256


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values] if norm else values


def build_style_vector(profile: ContentDNAProfile) -> list[float]:
    traits = {trait.name: trait.score for trait in profile.traits}
    values = [
        profile.lexical_diversity,
        min(profile.mean_sentence_length / 40, 1),
        min(profile.mean_paragraphs / 8, 1),
        min(profile.uppercase_ratio * 10, 1),
        min(profile.emoji_rate / 3, 1),
        min(profile.question_rate / 2, 1),
        min(profile.exclamation_rate / 3, 1),
        min(profile.ellipsis_rate / 2, 1),
        min(profile.dash_rate / 4, 1),
        profile.link_rate,
        profile.direct_address_rate,
        traits.get("Формальность", 0.0),
        traits.get("Эмоциональность", 0.0),
        traits.get("Диалогичность", 0.0),
        traits.get("Структурированность", 0.0),
        traits.get("Ссылочность", 0.0),
    ]
    return _normalize(values)


def build_temporal_vector(snapshot: ChannelSnapshot) -> list[float]:
    values = [0.0] * 168
    for post in snapshot.posts:
        values[post.published_at.weekday() * 24 + post.published_at.hour] += 1
    return _normalize(values)


def build_structural_vector(snapshot: ChannelSnapshot) -> list[float]:
    posts = snapshot.posts
    if not posts:
        return [0.0] * 8
    lengths = [len(post.text) for post in posts]
    values = [
        min(mean(lengths) / 3000, 1),
        sum(length < 300 for length in lengths) / len(posts),
        sum(length >= 1000 for length in lengths) / len(posts),
        sum("http" in p.text or "t.me/" in p.text for p in posts) / len(posts),
        sum("\n" in p.text for p in posts) / len(posts),
        sum("?" in p.text for p in posts) / len(posts),
        sum("!" in p.text for p in posts) / len(posts),
        sum((p.forwards or 0) > 0 or (p.reactions or 0) > 0 for p in posts) / len(posts),
    ]
    return _normalize(values)


def build_narrative_vector(snapshot: ChannelSnapshot, dimensions: int = 64) -> list[float]:
    counts = Counter(token.lower() for post in snapshot.posts for token in _TOKEN_RE.findall(post.text))
    values = [0.0] * dimensions
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        sign = 1.0 if digest[0] % 2 == 0 else -1.0
        values[bucket] += sign * math.log1p(count)
    return _normalize(values)


def build_intelligence_profile(snapshot: ChannelSnapshot, content_dna: ContentDNAProfile, metrics: dict[str, object]) -> IntelligenceProfile:
    style = build_style_vector(content_dna)
    temporal = build_temporal_vector(snapshot)
    structural = build_structural_vector(snapshot)
    narrative = build_narrative_vector(snapshot)
    combined = _normalize(style + temporal + structural + narrative)
    if len(combined) != VECTOR_DIM:
        raise RuntimeError(f"Некорректная размерность профиля: {len(combined)}")
    confidence = min(1.0, 0.65 * content_dna.confidence + 0.35 * min(len(snapshot.posts) / 120, 1.0))
    return IntelligenceProfile(
        username=snapshot.username,
        title=snapshot.title,
        subscribers=snapshot.subscribers,
        collected_at=snapshot.collected_at,
        source_post_count=len(snapshot.posts),
        methodology_version="intelligence-profile-v1",
        style_vector=tuple(style), temporal_vector=tuple(temporal), structural_vector=tuple(structural),
        narrative_vector=tuple(narrative), combined_vector=tuple(combined), metrics=metrics,
        content_dna=content_dna.to_dict(), confidence=round(confidence, 4),
    )
