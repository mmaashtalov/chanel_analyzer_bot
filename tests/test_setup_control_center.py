import json
from pathlib import Path

import pytest

from app.setup import server


def valid_config():
    return {
        "telegram_bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd",
        "telegram_api_id": 123456,
        "telegram_api_hash": "0123456789abcdef0123456789abcdef",
        "telegram_string_session": "1A-long-valid-telethon-string-session-value",
        "database_url": "postgresql+asyncpg://postgres:postgres@db:5432/osint",
        "data_provider": "telethon",
        "analysis_lookback_days": 30,
        "analysis_max_posts": 500,
    }


def test_validate_config_rejects_invalid_secrets():
    with pytest.raises(ValueError):
        server.validate_config({"telegram_bot_token": "bad", "database_url": "sqlite:///x"})


def test_validate_and_mask_config():
    cfg = server.validate_config(valid_config())
    public = server.public_config(cfg)
    assert public["telegram_bot_token_configured"] is True
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in json.dumps(public)
    assert public["telegram_api_id"] == 123456


def test_atomic_config_permissions(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "CONFIG_FILE", config_file)
    manager = server.ProductManager()
    manager.save(valid_config())
    assert config_file.exists()
    assert config_file.stat().st_mode & 0o777 == 0o600
    saved = json.loads(config_file.read_text())
    assert saved["telegram_bot_token"].startswith("123456789:")


def test_config_to_env_sets_production_mode():
    env = server.config_to_env(server.validate_config(valid_config()))
    assert env["APP_MODE"] == "production"
    assert env["TELEGRAM_API_ID"] == "123456"
    assert env["MONITORING_ENABLED"] == "true"
