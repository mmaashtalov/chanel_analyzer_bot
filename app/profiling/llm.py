from __future__ import annotations

from typing import Protocol

from app.domain.models import ChannelSnapshot
from app.profiling.models import ContentDNAProfile


class ContentDNAEnricher(Protocol):
    """Optional provider-neutral boundary for later LLM enrichment."""

    async def enrich(
        self,
        snapshot: ChannelSnapshot,
        deterministic_profile: ContentDNAProfile,
    ) -> ContentDNAProfile: ...


class PassthroughEnricher:
    async def enrich(
        self,
        snapshot: ChannelSnapshot,
        deterministic_profile: ContentDNAProfile,
    ) -> ContentDNAProfile:
        return deterministic_profile
