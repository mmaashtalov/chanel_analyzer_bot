from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    telegram_bot_token: str = Field(min_length=1)
    database_url: str
    data_provider: str = "not_configured"
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_string_session: str | None = None
    analysis_lookback_days: int = Field(default=365, ge=1, le=3650)
    analysis_max_posts: int = Field(default=5000, ge=50, le=100000)
    report_output_dir: Path = Path("/data/reports")
    monitoring_enabled: bool = True
    monitoring_poll_seconds: int = Field(default=60, ge=30, le=3600)
    evidence_acquisition_enabled: bool = True
    evidence_acquisition_poll_seconds: int = Field(default=60, ge=30, le=3600)
    evidence_acquisition_lookback_days: int = Field(default=30, ge=1, le=365)
    evidence_acquisition_max_sources: int = Field(default=10, ge=1, le=50)
    evidence_acquisition_max_documents_per_source: int = Field(default=50, ge=1, le=500)
    evidence_acquisition_timeout_seconds: int = Field(default=30, ge=5, le=120)
    evidence_acquisition_max_feed_bytes: int = Field(default=5_000_000, ge=100_000, le=25_000_000)
    evidence_acquisition_backoff_seconds: int = Field(default=60, ge=30, le=3600)

    @field_validator("data_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"telethon", "not_configured"}:
            raise ValueError("DATA_PROVIDER должен быть telethon или not_configured")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
