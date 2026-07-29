from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.sources.models import SourceType, UnifiedDocument


@dataclass(slots=True, frozen=True)
class SourceRequest:
    source_id: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int | None = None


@dataclass(slots=True, frozen=True)
class SourceHealth:
    healthy: bool
    adapter: str
    version: str
    details: str = ""


class SourceAdapter(Protocol):
    source_type: SourceType
    name: str
    version: str

    async def collect(self, request: SourceRequest) -> tuple[UnifiedDocument, ...]: ...

    async def healthcheck(self) -> SourceHealth: ...

    async def close(self) -> None: ...
