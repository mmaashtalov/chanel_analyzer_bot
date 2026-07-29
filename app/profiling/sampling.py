from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from app.domain.models import PostSnapshot


@dataclass(slots=True, frozen=True)
class SampledPost:
    post: PostSnapshot
    reasons: tuple[str, ...]


def build_stratified_sample(
    posts: tuple[PostSnapshot, ...],
    target_size: int = 180,
) -> tuple[SampledPost, ...]:
    """Select a reproducible sample across time, reach and text length."""
    candidates = [post for post in posts if post.text.strip()]
    if len(candidates) <= target_size:
        return tuple(SampledPost(post, ("all_posts",)) for post in sorted(candidates, key=lambda p: p.published_at))

    selected: dict[int, set[str]] = defaultdict(set)

    def add(items: list[PostSnapshot], reason: str, limit: int) -> None:
        for post in items[:limit]:
            selected[post.message_id].add(reason)

    quota = max(8, target_size // 8)
    add(sorted(candidates, key=lambda p: len(p.text), reverse=True), "long", quota)
    add(sorted(candidates, key=lambda p: len(p.text)), "short", quota)
    add(sorted(candidates, key=lambda p: p.views or -1, reverse=True), "high_reach", quota)
    add(sorted(candidates, key=lambda p: p.views if p.views is not None else 10**18), "low_reach", quota)

    # Temporal coverage: one representative per calendar week, then rotate hours/weekdays.
    by_week: dict[tuple[int, int], list[PostSnapshot]] = defaultdict(list)
    for post in candidates:
        iso = post.published_at.isocalendar()
        by_week[(iso.year, iso.week)].append(post)
    for week_posts in by_week.values():
        chosen = sorted(week_posts, key=lambda p: p.published_at)[len(week_posts) // 2]
        selected[chosen.message_id].add("temporal_coverage")

    for weekday in range(7):
        group = [p for p in candidates if p.published_at.weekday() == weekday]
        add(sorted(group, key=lambda p: p.published_at), f"weekday_{weekday}", 3)
    for bucket in range(0, 24, 4):
        group = [p for p in candidates if bucket <= p.published_at.hour < bucket + 4]
        add(sorted(group, key=lambda p: p.published_at), f"hour_{bucket:02d}", 3)

    # Fill deterministically around median length and across chronology.
    med = median(len(p.text) for p in candidates)
    fillers = sorted(candidates, key=lambda p: (abs(len(p.text) - med), p.published_at))
    for post in fillers:
        if len(selected) >= target_size:
            break
        selected[post.message_id].add("representative")

    chosen_posts = [p for p in candidates if p.message_id in selected]
    chosen_posts.sort(key=lambda p: p.published_at)
    if len(chosen_posts) > target_size:
        # Evenly retain the requested number without random state.
        indexes = {round(i * (len(chosen_posts) - 1) / (target_size - 1)) for i in range(target_size)}
        chosen_posts = [post for i, post in enumerate(chosen_posts) if i in indexes]

    return tuple(
        SampledPost(post, tuple(sorted(selected[post.message_id])))
        for post in chosen_posts
    )
