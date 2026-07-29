from __future__ import annotations

import re

from app.collection.base import ChannelDataProvider
from app.domain.models import ChannelRef
from app.sources.base import SourceHealth, SourceRequest
from app.sources.models import SourceType, UnifiedDocument

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)
_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,})")


class TelegramSourceAdapter:
    source_type = SourceType.TELEGRAM
    name = "telethon-channel-adapter"
    version = "1.0.0"

    def __init__(self, provider: ChannelDataProvider) -> None:
        self._provider = provider

    async def collect(self, request: SourceRequest) -> tuple[UnifiedDocument, ...]:
        channel = ChannelRef(request.source_id)
        snapshot = await self._provider.fetch_channel(
            channel, date_from=request.date_from, date_to=request.date_to
        )
        posts = snapshot.posts[: request.limit] if request.limit else snapshot.posts
        return tuple(
            UnifiedDocument(
                source_type=self.source_type,
                source_id=snapshot.username,
                document_id=str(post.message_id),
                body=post.text,
                published_at=post.published_at,
                title="",
                author=snapshot.title,
                canonical_url=post.url,
                links=tuple(_URL_RE.findall(post.text)),
                hashtags=tuple(match.group(1).casefold() for match in _HASHTAG_RE.finditer(post.text)),
                mentions=tuple(match.group(1).casefold() for match in _MENTION_RE.finditer(post.text)),
                metadata={
                    "views": post.views,
                    "reactions": post.reactions,
                    "forwards": post.forwards,
                    "subscribers": snapshot.subscribers,
                },
            )
            for post in posts
        )

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(True, self.name, self.version, "provider configured")

    async def close(self) -> None:
        await self._provider.close()
