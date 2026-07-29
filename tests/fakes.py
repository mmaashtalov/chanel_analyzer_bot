from datetime import UTC, datetime

from app.domain.models import ChannelRef, ChannelSnapshot, PostSnapshot


class FakeProvider:
    async def fetch_channel(self, channel: ChannelRef, date_from=None, date_to=None) -> ChannelSnapshot:
        posts = tuple(
            PostSnapshot(
                message_id=index,
                published_at=datetime(2026, 1, 1 + index % 20, index % 24, tzinfo=UTC),
                text=("Тестовый аналитический пост " * (index % 30 + 1)).strip(),
                views=1000 + index * 30,
                reactions=10 + index % 50,
                forwards=index % 12,
                url=f"https://t.me/{channel.username}/{index}",
            )
            for index in range(1, 80)
        )
        return ChannelSnapshot(channel.username, "Тестовый канал", 10000, datetime.now(UTC), posts)

    async def close(self) -> None:
        return None
