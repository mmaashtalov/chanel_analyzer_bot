from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class AnalysisType(StrEnum):
    QUANTITATIVE = "quantitative"
    FULL = "full"
    COMPARE = "compare"
    NETWORK = "network"


class JobStatus(StrEnum):
    PENDING = "pending"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class ChannelRef:
    username: str

    def __post_init__(self) -> None:
        value = self.username.strip()
        for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"): 
            if value.startswith(prefix):
                value = value.removeprefix(prefix)
                break
        value = value.split("?", maxsplit=1)[0].strip("/")
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("Некорректный Telegram username")
        if not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError("Username может содержать только буквы, цифры и подчёркивание")
        object.__setattr__(self, "username", value)


@dataclass(slots=True, frozen=True)
class PostSnapshot:
    message_id: int
    published_at: datetime
    text: str
    views: int | None = None
    reactions: int | None = None
    forwards: int | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            object.__setattr__(self, "published_at", self.published_at.replace(tzinfo=UTC))


@dataclass(slots=True, frozen=True)
class ChannelSnapshot:
    username: str
    title: str
    subscribers: int | None
    collected_at: datetime
    posts: tuple[PostSnapshot, ...] = field(default_factory=tuple)
