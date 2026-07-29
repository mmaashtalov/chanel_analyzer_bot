from __future__ import annotations

import math
import re
from collections import Counter
from statistics import mean

from app.analytics.advanced import calculate_advanced
from app.domain.models import ChannelSnapshot
from app.profiling.models import ContentDNAProfile
from app.similarity.models import SimilarityEvidence, SimilarityResult

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{3,}")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return _clamp(dot / (norm_a * norm_b))


def _style_vector(profile: ContentDNAProfile) -> list[float]:
    trait_map = {trait.name: trait.score for trait in profile.traits}
    return [
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
        *[trait_map.get(name, 0.0) for name in (
            "Формальность", "Эмоциональность", "Диалогичность", "Структурированность", "Ссылочность"
        )],
    ]


def _temporal_vector(snapshot: ChannelSnapshot) -> list[float]:
    bins = [0.0] * (7 * 24)
    for post in snapshot.posts:
        bins[post.published_at.weekday() * 24 + post.published_at.hour] += 1
    total = sum(bins)
    return [value / total for value in bins] if total else bins


def _structural_vector(snapshot: ChannelSnapshot) -> list[float]:
    posts = snapshot.posts
    if not posts:
        return [0.0] * 8
    lengths = [len(post.text) for post in posts]
    link_share = sum("http" in post.text or "t.me/" in post.text for post in posts) / len(posts)
    newline_share = sum("\n" in post.text for post in posts) / len(posts)
    question_share = sum("?" in post.text for post in posts) / len(posts)
    exclamation_share = sum("!" in post.text for post in posts) / len(posts)
    forward_share = sum((post.forwards or 0) > 0 for post in posts) / len(posts)
    reaction_share = sum((post.reactions or 0) > 0 for post in posts) / len(posts)
    return [
        min(mean(lengths) / 3000, 1),
        sum(length < 300 for length in lengths) / len(posts),
        sum(length >= 1000 for length in lengths) / len(posts),
        link_share,
        newline_share,
        question_share,
        exclamation_share,
        (forward_share + reaction_share) / 2,
    ]


def _narrative_score(a: ChannelSnapshot, b: ChannelSnapshot) -> tuple[float, tuple[str, ...]]:
    terms_a = dict(calculate_advanced(a).top_terms[:40])
    terms_b = dict(calculate_advanced(b).top_terms[:40])
    vocabulary = sorted(set(terms_a) | set(terms_b))
    if not vocabulary:
        return 0.0, ()
    score = _cosine([float(terms_a.get(term, 0)) for term in vocabulary], [float(terms_b.get(term, 0)) for term in vocabulary])
    common = sorted(set(terms_a) & set(terms_b), key=lambda term: terms_a[term] + terms_b[term], reverse=True)
    return score, tuple(common[:8])


def _representative_ids(snapshot: ChannelSnapshot, predicate, limit: int = 3) -> tuple[int, ...]:
    return tuple(post.message_id for post in snapshot.posts if predicate(post))[:limit]


def compare_channels(
    snapshot_a: ChannelSnapshot,
    profile_a: ContentDNAProfile,
    snapshot_b: ChannelSnapshot,
    profile_b: ContentDNAProfile,
) -> SimilarityResult:
    style = _cosine(_style_vector(profile_a), _style_vector(profile_b))
    temporal = _cosine(_temporal_vector(snapshot_a), _temporal_vector(snapshot_b))
    structural = _cosine(_structural_vector(snapshot_a), _structural_vector(snapshot_b))
    narrative, common_terms = _narrative_score(snapshot_a, snapshot_b)

    overall = 0.35 * style + 0.20 * narrative + 0.20 * temporal + 0.25 * structural
    data_factor = min(1.0, min(len(snapshot_a.posts), len(snapshot_b.posts)) / 120)
    confidence = _clamp(0.55 * min(profile_a.confidence, profile_b.confidence) + 0.45 * data_factor)

    dimensions = {
        "стилю": style,
        "тематике": narrative,
        "ритму публикаций": temporal,
        "структуре постов": structural,
    }
    strongest = sorted(dimensions.items(), key=lambda item: item[1], reverse=True)[:2]
    weakest = min(dimensions.items(), key=lambda item: item[1])
    explanation = (
        f"Наибольшее сходство наблюдается по {strongest[0][0]} ({strongest[0][1]:.0%}) "
        f"и {strongest[1][0]} ({strongest[1][1]:.0%}). "
        f"Наименее выражено совпадение по {weakest[0]} ({weakest[1]:.0%}). "
        "Результат описывает сходство публикационных профилей и не доказывает общего автора или владельца."
    )

    common_markers = tuple(sorted(set(profile_a.dominant_markers) & set(profile_b.dominant_markers)))
    evidence: list[SimilarityEvidence] = []
    if common_terms:
        evidence.append(SimilarityEvidence("narrative", "Общие частотные термины: " + ", ".join(common_terms)))
    if common_markers:
        evidence.append(SimilarityEvidence("style", "Общие стилевые маркеры: " + ", ".join(common_markers)))
    evidence.append(
        SimilarityEvidence(
            "structure",
            "Примеры длинных или структурированных публикаций в обеих выборках.",
            _representative_ids(snapshot_a, lambda p: len(p.text) >= 800 or "\n" in p.text),
            _representative_ids(snapshot_b, lambda p: len(p.text) >= 800 or "\n" in p.text),
        )
    )

    alternatives = (
        "Общая тематика или единый новостной контекст могут повышать семантическое сходство.",
        "Редакционные шаблоны, автопостинг или общие источники могут создавать сходство без общего авторства.",
        "Небольшая или неоднородная выборка снижает устойчивость оценки.",
    )
    return SimilarityResult(
        snapshot_a.username,
        snapshot_b.username,
        round(style, 4),
        round(narrative, 4),
        round(temporal, 4),
        round(structural, 4),
        round(overall, 4),
        round(confidence, 4),
        explanation,
        alternatives,
        tuple(evidence),
    )
