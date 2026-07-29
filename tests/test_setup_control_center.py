import json

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
    assert "local-product-password" not in json.dumps(public)
    assert "database_url" not in public
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


def test_credential_check_reports_fields_without_returning_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CONFIG_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "control-center.log")
    manager = server.ProductManager()

    result = manager.credential_check(valid_config())

    assert result["status"] == "ok"
    assert result["checks"]["telegram_bot_token"]["status"] == "ok"
    serialized = json.dumps(result, ensure_ascii=False)
    assert valid_config()["telegram_bot_token"] not in serialized
    assert valid_config()["telegram_string_session"] not in serialized


def test_operation_state_survives_control_center_restart(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.json"
    log_file = tmp_path / "control-center.log"
    monkeypatch.setattr(server, "CONFIG_FILE", config_file)
    monkeypatch.setattr(server, "LOG_FILE", log_file)
    first = server.ProductManager()
    first.state.update({"status": "error", "last_error": "collector failed", "last_exit_code": 17})
    first._persist_state()

    second = server.ProductManager()

    assert second.state["status"] == "error"
    assert second.state["last_error"] == "collector failed"
    assert second.last_exit_code == 17


def test_backup_integrity_and_restore(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.json"
    log_file = tmp_path / "control-center.log"
    monkeypatch.setattr(server, "CONFIG_FILE", config_file)
    monkeypatch.setattr(server, "LOG_FILE", log_file)
    manager = server.ProductManager()
    manager.save(valid_config())

    content, filename, digest = manager.backup_download()
    payload = json.loads(content)
    assert filename.endswith(".json")
    assert payload["integrity_sha256"] == digest
    assert server.verify_backup(payload)["config"]["telegram_api_id"] == 123456

    payload["config"]["analysis_max_posts"] = 6000
    with pytest.raises(ValueError, match="SHA-256"):
        server.verify_backup(payload)

    restored = manager.restore(json.loads(content))
    assert restored["status"] == "ok"
    assert json.loads(config_file.read_text())["telegram_api_id"] == 123456
