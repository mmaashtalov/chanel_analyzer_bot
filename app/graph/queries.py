from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class EntityChannelStat:
    channel_username: str
    mentions: int
    posts: int
    first_seen: datetime
    last_seen: datetime


@dataclass(slots=True, frozen=True)
class EntitySummary:
    entity_type: str
    canonical_name: str
    display_name: str
    total_mentions: int
    post_count: int
    channel_count: int
    channels: tuple[EntityChannelStat, ...]


@dataclass(slots=True, frozen=True)
class TimelineBucket:
    period: str
    mentions: int
    posts: int
