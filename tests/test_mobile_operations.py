import json

from app.setup import server


def valid_config():
    return {
        "telegram_bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd",
        "telegram_api_id": 123456,
        "telegram_api_hash": "0123456789abcdef0123456789abcdef",
        "telegram_string_session": "1A-long-valid-telethon-string-session-value",
        "database_url": "postgresql+asyncpg://postgres:local-product-password@db:5432/osint",
        "data_provider": "telethon",
        "analysis_lookback_days": 30,
        "analysis_max_posts": 5000,
    }


def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CONFIG_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "control-center.log")
    instance = server.ProductManager()
    instance.save(valid_config())
    return instance


def test_diagnostics_redacts_database_password_and_reports_unapplied_migration(tmp_path, monkeypatch):
    instance = manager(tmp_path, monkeypatch)

    report = instance.diagnostics()

    assert report["status"] in {"ok", "attention"}
    assert report["checks"]["configuration"]["status"] == "ok"
    assert report["checks"]["migration"]["status"] == "pending"
    assert "local-product-password" not in json.dumps(report, ensure_ascii=False)


def test_update_prepare_creates_recoverable_backup(tmp_path, monkeypatch):
    instance = manager(tmp_path, monkeypatch)

    result = instance.prepare_update()

    assert result["status"] == "ready"
    assert result["requires_redeploy"] is True
    backup_path = tmp_path / "backups" / result["backup_file"]
    assert backup_path.exists()
    assert json.loads(backup_path.read_text())["integrity_sha256"] == result["backup_sha256"]
    assert instance.status()["status"] == "stopped"


def test_failed_migration_is_persisted_without_secret_output(tmp_path, monkeypatch):
    instance = manager(tmp_path, monkeypatch)

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "postgresql+asyncpg://postgres:local-product-password@db:5432/osint migration failed"

    monkeypatch.setattr(server.subprocess, "run", lambda *args, **kwargs: Failed())

    try:
        instance.migrate()
    except RuntimeError as exc:
        assert "local-product-password" not in str(exc)
    else:
        raise AssertionError("migration should fail")

    assert instance.state["migration"]["status"] == "error"
    assert "local-product-password" not in (tmp_path / "control-center.log").read_text()
