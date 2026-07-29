from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import mean, median, pstdev

from app.domain.models import ChannelSnapshot, PostSnapshot


@dataclass(slots=True, frozen=True)
class QuantitativeMetrics:
    posts_count: int
    period_from: datetime | None
    period_to: datetime | None
    mean_views: float | None
    median_views: float | None
    max_views: int | None
    mean_reactions: float | None
    mean_forwards: float | None
    mean_post_length: float
    engagement_per_1000_views: float | None
    posts_per_day: float | None
    median_interval_hours: float | None
    views_coefficient_of_variation: float | None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for key in ("period_from", "period_to"):
            value = payload[key]
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        return payload


def _values(posts: tuple[PostSnapshot, ...], field: str) -> list[int]:
    result: list[int] = []
    for post in posts:
        value = getattr(post, field)
        if value is not None:
            result.append(int(value))
    return result


def calculate_metrics(snapshot: ChannelSnapshot) -> QuantitativeMetrics:
    posts = tuple(sorted(snapshot.posts, key=lambda post: post.published_at))
    views = _values(posts, "views")
    reactions = _values(posts, "reactions")
    forwards = _values(posts, "forwards")
    total_views = sum(views)
    total_reactions = sum(reactions)
    period_from = posts[0].published_at if posts else None
    period_to = posts[-1].published_at if posts else None
    span_days = ((period_to - period_from).total_seconds() / 86400) if period_from and period_to else 0
    intervals = [
        (posts[index].published_at - posts[index - 1].published_at).total_seconds() / 3600
        for index in range(1, len(posts))
    ]
    views_cv = None
    if len(views) > 1 and mean(views) > 0:
        views_cv = pstdev(views) / mean(views)
    return QuantitativeMetrics(
        posts_count=len(posts),
        period_from=period_from,
        period_to=period_to,
        mean_views=mean(views) if views else None,
        median_views=median(views) if views else None,
        max_views=max(views) if views else None,
        mean_reactions=mean(reactions) if reactions else None,
        mean_forwards=mean(forwards) if forwards else None,
        mean_post_length=mean([len(post.text) for post in posts]) if posts else 0.0,
        engagement_per_1000_views=(total_reactions / total_views * 1000) if total_views else None,
        posts_per_day=(len(posts) / max(span_days, 1.0)) if posts else None,
        median_interval_hours=median(intervals) if intervals else None,
        views_coefficient_of_variation=views_cv,
    )
