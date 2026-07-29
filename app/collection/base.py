from datetime import datetime
from typing import Protocol

from app.domain.models import ChannelRef, ChannelSnapshot


class ChannelDataProvider(Protocol):
    async def fetch_channel(
        self,
        channel: ChannelRef,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ChannelSnapshot: ...

    async def close(self) -> None: ...


class ProviderError(RuntimeError):
    pass


class ProviderNotConfiguredError(ProviderError):
    pass


class ChannelNotFoundError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class NotConfiguredProvider:
    async def fetch_channel(
        self,
        channel: ChannelRef,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ChannelSnapshot:
        raise ProviderNotConfiguredError(
            "Источник Telegram-данных не настроен. Укажите DATA_PROVIDER=telethon и MTProto-секреты."
        )

    async def close(self) -> None:
        return None
