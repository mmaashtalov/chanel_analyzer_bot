from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean, median

import numpy as np

from app.domain.models import ChannelSnapshot, PostSnapshot

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]{3,}")
_STOPWORDS = {
    "это", "как", "для", "или", "при", "что", "все", "его", "она", "они", "мы", "вы",
    "так", "уже", "еще", "ещё", "только", "были", "было", "будет", "есть", "нет", "под",
    "над", "без", "про", "через", "после", "перед", "между", "свой", "свои", "этот", "эта",
    "the", "and", "for", "with", "from", "this", "that", "are", "was", "were", "have",
}


@dataclass(slots=True, frozen=True)
class Anomaly:
    message_id: int
    kind: str
    score: float
    reason: str
    url: str | None


@dataclass(slots=True, frozen=True)
class AdvancedAnalytics:
    q25_views: float | None
    q75_views: float | None
    p90_views: float | None
    publishing_stability: float | None
    longest_silence_hours: float | None
    burst_days: tuple[str, ...]
    length_views_correlation: float | None
    length_engagement_correlation: float | None
    links_engagement_correlation: float | None
    best_weekday: int | None
    best_hour: int | None
    top_terms: tuple[tuple[str, int], ...]
    top_bigrams: tuple[tuple[str, int], ...]
    anomalies: tuple[Anomaly, ...]
    executive_summary: tuple[str, ...]


def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    value = float(np.corrcoef(xs, ys)[0, 1])
    return None if math.isnan(value) else value


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS]


def _post_engagement(post: PostSnapshot) -> float | None:
    if not post.views:
        return None
    return ((post.reactions or 0) + (post.forwards or 0)) / post.views * 1000


def calculate_advanced(snapshot: ChannelSnapshot) -> AdvancedAnalytics:
    posts = sorted(snapshot.posts, key=lambda p: p.published_at)
    views = [float(p.views) for p in posts if p.views is not None]
    q25 = float(np.percentile(views, 25)) if views else None
    q75 = float(np.percentile(views, 75)) if views else None
    p90 = float(np.percentile(views, 90)) if views else None

    intervals = [
        (posts[i].published_at - posts[i - 1].published_at).total_seconds() / 3600
        for i in range(1, len(posts))
    ]
    stability = None
    if intervals and mean(intervals) > 0:
        stability = max(0.0, 1.0 - min(1.0, float(np.std(intervals)) / mean(intervals)))

    by_day: dict[str, list[PostSnapshot]] = defaultdict(list)
    for post in posts:
        by_day[post.published_at.date().isoformat()].append(post)
    counts = [len(v) for v in by_day.values()]
    burst_days: list[str] = []
    if counts:
        threshold = mean(counts) + 2 * float(np.std(counts))
        burst_days = [day for day, values in by_day.items() if len(values) >= max(3, threshold)]

    lengths, corr_views, corr_eng = [], [], []
    link_counts, link_eng = [], []
    for post in posts:
        if post.views is not None:
            lengths.append(float(len(post.text)))
            corr_views.append(float(post.views))
        engagement = _post_engagement(post)
        if engagement is not None:
            corr_eng.append(engagement)
            link_counts.append(float(len(re.findall(r"https?://|t\.me/", post.text))))
            link_eng.append(engagement)
    # Align length/engagement independently.
    le_x, le_y = [], []
    for post in posts:
        engagement = _post_engagement(post)
        if engagement is not None:
            le_x.append(float(len(post.text)))
            le_y.append(engagement)

    weekday_views: dict[int, list[int]] = defaultdict(list)
    hour_views: dict[int, list[int]] = defaultdict(list)
    for post in posts:
        if post.views is not None:
            weekday_views[post.published_at.weekday()].append(post.views)
            hour_views[post.published_at.hour].append(post.views)
    best_weekday = max(weekday_views, key=lambda k: mean(weekday_views[k])) if weekday_views else None
    best_hour = max(hour_views, key=lambda k: mean(hour_views[k])) if hour_views else None

    terms = Counter()
    bigrams = Counter()
    for post in posts:
        tokens = _tokens(post.text)
        terms.update(tokens)
        bigrams.update(zip(tokens, tokens[1:]))

    anomalies: list[Anomaly] = []
    if len(views) >= 5:
        med = median(views)
        mad = median([abs(v - med) for v in views]) or 1.0
        for post in posts:
            if post.views is None:
                continue
            score = 0.6745 * (post.views - med) / mad
            if abs(score) >= 3.5:
                kind = "outperformer" if score > 0 else "underperformer"
                anomalies.append(Anomaly(
                    post.message_id,
                    kind,
                    round(abs(score), 2),
                    f"Охват отклоняется от медианы на {abs(score):.1f} MAD",
                    post.url,
                ))
    anomalies.sort(key=lambda item: item.score, reverse=True)

    weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    summary: list[str] = []
    summary.append(f"Проанализировано {len(posts)} публикаций канала @{snapshot.username}.")
    if best_weekday is not None and best_hour is not None:
        summary.append(f"Наиболее результативное окно: {weekday_names[best_weekday]}, около {best_hour:02d}:00 UTC.")
    lv_corr = _corr(lengths, corr_views)
    if lv_corr is not None:
        direction = "положительная" if lv_corr > 0.2 else "отрицательная" if lv_corr < -0.2 else "слабая"
        summary.append(f"Связь длины поста и охвата: {direction} (r={lv_corr:.2f}).")
    if stability is not None:
        label = "высокая" if stability >= 0.7 else "средняя" if stability >= 0.4 else "низкая"
        summary.append(f"Регулярность публикаций: {label} ({stability:.0%}).")
    if anomalies:
        summary.append(f"Обнаружено {len(anomalies)} статистически аномальных публикаций.")
    if burst_days:
        summary.append(f"Зафиксировано {len(burst_days)} дней с аномально высокой частотой постинга.")

    return AdvancedAnalytics(
        q25_views=q25,
        q75_views=q75,
        p90_views=p90,
        publishing_stability=stability,
        longest_silence_hours=max(intervals) if intervals else None,
        burst_days=tuple(burst_days),
        length_views_correlation=lv_corr,
        length_engagement_correlation=_corr(le_x, le_y),
        links_engagement_correlation=_corr(link_counts, link_eng),
        best_weekday=best_weekday,
        best_hour=best_hour,
        top_terms=tuple(terms.most_common(25)),
        top_bigrams=tuple((" ".join(pair), count) for pair, count in bigrams.most_common(15)),
        anomalies=tuple(anomalies[:20]),
        executive_summary=tuple(summary),
    )
