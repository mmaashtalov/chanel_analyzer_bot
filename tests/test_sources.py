from datetime import UTC, datetime

import pytest

from app.domain.models import ChannelSnapshot, PostSnapshot
from app.sources import SourceRegistry, SourceRequest, SourceType, UnifiedDocument, deduplicate_exact, group_cross_source_duplicates
from app.sources.adapters import RSSSourceAdapter, TelegramSourceAdapter


class FakeTelegramProvider:
    async def fetch_channel(self, channel, date_from=None, date_to=None):
        return ChannelSnapshot(
            username=channel.username,
            title="Demo",
            subscribers=100,
            collected_at=datetime.now(UTC),
            posts=(
                PostSnapshot(
                    message_id=1,
                    published_at=datetime(2026, 1, 1, 10, tzinfo=UTC),
                    text="Новость #Тест @source https://example.com/a",
                    views=10,
                    reactions=2,
                    forwards=1,
                    url="https://t.me/demo/1",
                ),
            ),
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_telegram_adapter_normalizes_snapshot():
    adapter = TelegramSourceAdapter(FakeTelegramProvider())
    docs = await adapter.collect(SourceRequest("@demo"))
    assert len(docs) == 1
    doc = docs[0]
    assert doc.source_type is SourceType.TELEGRAM
    assert doc.document_id == "1"
    assert doc.hashtags == ("тест",)
    assert doc.mentions == ("source",)
    assert doc.metadata["views"] == 10


@pytest.mark.asyncio
async def test_rss_adapter_parses_rss_and_atom_dates():
    payload = b"""<?xml version='1.0'?>
    <rss version='2.0'><channel><item>
      <title>Item</title><description>Body</description>
      <link>https://example.com/item</link><guid>x1</guid>
      <pubDate>Wed, 01 Jan 2026 10:00:00 +0000</pubDate>
    </item></channel></rss>"""

    async def fetcher(url: str) -> bytes:
        assert url == "https://example.com/feed"
        return payload

    adapter = RSSSourceAdapter(fetcher)
    docs = await adapter.collect(SourceRequest("https://example.com/feed"))
    assert docs[0].title == "Item"
    assert docs[0].canonical_url == "https://example.com/item"
    assert docs[0].published_at.year == 2026


def test_fingerprints_are_stable_and_cross_source_aware():
    kwargs = dict(
        document_id="1",
        body="  Одна   и та же НОВОСТЬ ",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        links=("HTTPS://EXAMPLE.COM/a/",),
    )
    telegram = UnifiedDocument(SourceType.TELEGRAM, "demo", **kwargs)
    rss = UnifiedDocument(SourceType.RSS, "feed", **kwargs)
    assert telegram.fingerprint != rss.fingerprint
    assert telegram.content_fingerprint == rss.content_fingerprint


def test_deduplication_and_cross_source_grouping():
    published = datetime(2026, 1, 1, tzinfo=UTC)
    first = UnifiedDocument(SourceType.TELEGRAM, "demo", "1", "same", published)
    exact = UnifiedDocument(SourceType.TELEGRAM, "demo", "1", "same", published)
    other = UnifiedDocument(SourceType.RSS, "feed", "2", "same", published)
    assert len(deduplicate_exact((first, exact, other))) == 2
    groups = group_cross_source_duplicates((first, other))
    assert len(groups) == 1
    assert len(groups[0].documents) == 2


@pytest.mark.asyncio
async def test_registry_registers_and_reports_health():
    registry = SourceRegistry()
    registry.register(TelegramSourceAdapter(FakeTelegramProvider()))
    assert registry.available() == (SourceType.TELEGRAM,)
    assert registry.get("telegram").name == "telethon-channel-adapter"
    health = await registry.health()
    assert health["telegram"].healthy is True
    with pytest.raises(ValueError):
        registry.register(TelegramSourceAdapter(FakeTelegramProvider()))
