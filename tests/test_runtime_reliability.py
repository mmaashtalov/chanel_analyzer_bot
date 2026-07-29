from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

from app.core.runtime import RuntimeHeartbeat, inspect_runtime_health, load_runtime_health
from app.setup import server


def _configure_manager_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "CONFIG_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "config" / "control-center.log")
    monkeypatch.setattr(server, "RUNTIME_DIR", tmp_path / "runtime")


def test_runtime_heartbeat_is_durable_secret_free_and_fresh(tmp_path):
    path = tmp_path / "runtime-health.json"
    heartbeat = RuntimeHeartbeat(path, run_id="run-24")
    heartbeat.start()
    heartbeat.beat({"telegram_updater": "running", "monitoring_worker": "running"})

    payload = load_runtime_health(path)
    status = inspect_runtime_health(payload)

    assert path.stat().st_mode & 0o777 == 0o600
    assert status["status"] == "healthy"
    assert status["run_id"] == "run-24"
    assert status["components"]["telegram_updater"] == "running"
    assert "token" not in json.dumps(payload, ensure_ascii=False).lower()


def test_runtime_heartbeat_marks_stale_without_using_process_state(tmp_path):
    path = tmp_path / "runtime-health.json"
    heartbeat = RuntimeHeartbeat(path, run_id="run-stale")
    payload = heartbeat.beat({"telegram_updater": "running"})
    observed_at = datetime.fromisoformat(payload["heartbeat_at"])

    status = inspect_runtime_health(
        payload,
        now=observed_at.astimezone(UTC) + timedelta(seconds=181),
        freshness_seconds=180,
    )

    assert status["status"] == "stale"
    assert status["age_seconds"] == 181


def test_control_center_exposes_runtime_health_without_credentials(tmp_path, monkeypatch):
    _configure_manager_paths(tmp_path, monkeypatch)
    heartbeat = RuntimeHeartbeat(server.RUNTIME_DIR / "runtime-health.json", run_id="run-owner")
    heartbeat.beat({"telegram_updater": "running"})
    manager = server.ProductManager()

    status = manager.status()

    assert status["runtime"]["status"] == "healthy"
    assert status["runtime"]["run_id"] == "run-owner"
    assert "run-owner" in json.dumps(status, ensure_ascii=False)


def test_watchdog_schedules_recovery_only_for_desired_running_state(tmp_path, monkeypatch):
    _configure_manager_paths(tmp_path, monkeypatch)
    manager = server.ProductManager()
    manager.state.update(
        {
            "status": "error",
            "desired_status": "running",
            "pid": None,
            "last_error": "collector exited",
        }
    )

    manager.watchdog_tick()

    recovery = manager.state["recovery"]
    assert recovery["next_retry_epoch"] is not None
    assert recovery["suppressed"] is False

    manager.state["desired_status"] = "stopped"
    manager.state["recovery"] = server._recovery_default()
    manager.watchdog_tick()
    assert manager.state["recovery"]["next_retry_epoch"] is None


def test_crash_loop_budget_requires_manual_start(tmp_path, monkeypatch):
    _configure_manager_paths(tmp_path, monkeypatch)
    manager = server.ProductManager()
    manager.state["desired_status"] = "running"
    manager.state["recovery"] = {
        "attempts": [time.time(), time.time(), time.time()],
        "next_retry_epoch": None,
        "suppressed": False,
        "last_reason": None,
    }

    manager._schedule_recovery("collector exited repeatedly")

    assert manager.state["recovery"]["suppressed"] is True
    assert manager.state["status"] == "error"
    assert "превышен лимит" in manager.state["last_error"]


def test_watchdog_executes_due_recovery_without_manual_intervention(tmp_path, monkeypatch):
    _configure_manager_paths(tmp_path, monkeypatch)
    manager = server.ProductManager()
    manager.state.update(
        {
            "status": "error",
            "desired_status": "running",
            "pid": None,
            "last_error": "collector exited",
            "recovery": {
                "attempts": [],
                "next_retry_epoch": time.time() - 1,
                "suppressed": False,
                "last_reason": "collector exited",
            },
        }
    )
    launched: dict[str, object] = {}

    monkeypatch.setattr(server, "validate_config", lambda _candidate, _existing=None: {})

    def fake_launch(config, operation_id, *, recovered):
        launched.update(config=config, operation_id=operation_id, recovered=recovered)
        manager.state.update({"status": "running", "pid": None})

    monkeypatch.setattr(manager, "_launch_product", fake_launch)

    manager.watchdog_tick()

    assert launched["config"] == {}
    assert launched["recovered"] is True
    assert len(manager.state["recovery"]["attempts"]) == 1


def test_owner_http_status_exposes_runtime_recovery(tmp_path, monkeypatch):
    _configure_manager_paths(tmp_path, monkeypatch)
    manager = server.ProductManager()
    monkeypatch.setattr(server, "MANAGER", manager)
    http = ThreadingHTTPServer(("127.0.0.1", 0), server.ControlHandler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{http.server_address[1]}"
        with urlopen(f"{base_url}/health", timeout=3) as response:
            health = json.loads(response.read())
        with urlopen(f"{base_url}/api/status", timeout=3) as response:
            status = json.loads(response.read())
    finally:
        http.shutdown()
        thread.join(timeout=3)
        http.server_close()

    assert health == {"status": "ok", "mode": "setup", "version": "0.24.0-product"}
    assert "runtime" in status
    assert "recovery" in status
