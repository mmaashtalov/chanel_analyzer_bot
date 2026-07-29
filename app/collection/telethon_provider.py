from datetime import UTC, datetime

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest

from app.collection.base import (
    ChannelNotFoundError,
    ProviderAuthenticationError,
    ProviderError,
)
from app.domain.models import ChannelRef, ChannelSnapshot, PostSnapshot


def _count_reactions(message: object) -> int | None:
    reactions = getattr(message, "reactions", None)
    results = getattr(reactions, "results", None) if reactions else None
    if not results:
        return None
    return sum(int(getattr(item, "count", 0) or 0) for item in results)


class TelethonChannelDataProvider:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        string_session: str,
        max_posts: int = 5000,
    ) -> None:
        if not string_session:
            raise ProviderAuthenticationError("TELEGRAM_STRING_SESSION не задан")
        self._client = TelegramClient(StringSession(string_session), api_id, api_hash)
        self._max_posts = max_posts
        self._started = False

    async def _ensure_started(self) -> None:
        if self._started:
            return
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise ProviderAuthenticationError("MTProto-сессия не авторизована")
        self._started = True

    async def fetch_channel(
        self,
        channel: ChannelRef,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ChannelSnapshot:
        await self._ensure_started()
        try:
            entity = await self._client.get_entity(channel.username)
            full = await self._client(GetFullChannelRequest(entity))
            subscribers = getattr(full.full_chat, "participants_count", None)
            title = str(getattr(entity, "title", channel.username))
            posts: list[PostSnapshot] = []
            async for message in self._client.iter_messages(
                entity,
                limit=self._max_posts,
                offset_date=date_to,
            ):
                published_at = message.date.astimezone(UTC)
                if date_from and published_at < date_from:
                    break
                if date_to and published_at > date_to:
                    continue
                # Service messages and empty media-only messages are intentionally skipped.
                text = (message.message or "").strip()
                if not text:
                    continue
                posts.append(
                    PostSnapshot(
                        message_id=int(message.id),
                        published_at=published_at,
                        text=text,
                        views=int(message.views) if message.views is not None else None,
                        reactions=_count_reactions(message),
                        forwards=int(message.forwards) if message.forwards is not None else None,
                        url=f"https://t.me/{channel.username}/{message.id}",
                    )
                )
            return ChannelSnapshot(
                username=channel.username,
                title=title,
                subscribers=int(subscribers) if subscribers is not None else None,
                collected_at=datetime.now(UTC),
                posts=tuple(reversed(posts)),
            )
        except (ValueError, errors.UsernameInvalidError, errors.UsernameNotOccupiedError) as exc:
            raise ChannelNotFoundError(f"Канал @{channel.username} не найден") from exc
        except errors.FloodWaitError as exc:
            raise ProviderError(f"Telegram ограничил запросы. Повторите через {exc.seconds} сек.") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Ошибка получения данных Telegram: {type(exc).__name__}") from exc

    async def close(self) -> None:
        if self._client.is_connected():
            await self._client.disconnect()
        self._started = False
