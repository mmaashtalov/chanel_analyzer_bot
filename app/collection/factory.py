from app.collection.base import ChannelDataProvider, NotConfiguredProvider
from app.collection.telethon_provider import TelethonChannelDataProvider
from app.core.config import Settings


def build_provider(settings: Settings) -> ChannelDataProvider:
    if settings.data_provider == "telethon":
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise RuntimeError("Для Telethon требуются TELEGRAM_API_ID и TELEGRAM_API_HASH")
        return TelethonChannelDataProvider(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            string_session=settings.telegram_string_session or "",
            max_posts=settings.analysis_max_posts,
        )
    return NotConfiguredProvider()
