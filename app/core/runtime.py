"""Durable, secret-free runtime health for the production bot process.

The Control Center is a separate process from the Telegram application.  A
live Control Center therefore does not prove that polling, workers and the
event loop are still live.  This module writes a small heartbeat to the
persistent runtime volume so the owner-facing operational layer can make that
distinction without reading process logs or credentials.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNTIME_HEALTH_SCHEMA = 1
DEFAULT_FRESHNESS_SECONDS = 180
_ALLOWED_STATUSES = {"starting", "running", "stopping", "stopped", "error"}


def utc_timestamp(now: datetime | None = None) -> str:
    """Return a stable UTC timestamp suitable for persisted operational state."""

    value = now or datetime.now(UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def runtime_directory() -> Path:
    """Resolve the persistent runtime directory without relying on app settings."""

    explicit = os.getenv("PRODUCT_RUNTIME_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return Path(os.getenv("DATA_DIR", "/data")) / "runtime"


def runtime_health_path() -> Path:
    return runtime_directory() / "runtime-health.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def load_runtime_health(path: Path | None = None) -> dict[str, Any]:
    """Load a runtime heartbeat, returning an empty mapping for unavailable data."""

    candidate = path or runtime_health_path()
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def inspect_runtime_health(
    payload: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> dict[str, Any]:
    """Return a bounded public view of a heartbeat and its freshness.

    The file is treated as operational evidence, not as a source of truth for
    credentials.  Only the defined public fields are returned.
    """

    data = dict(payload or {})
    if data.get("schema") != RUNTIME_HEALTH_SCHEMA:
        return {
            "status": "unavailable",
            "message": "runtime heartbeat ещё не создан",
            "age_seconds": None,
            "run_id": None,
            "heartbeat_at": None,
            "components": {},
            "last_error": None,
        }

    heartbeat_at = _parse_timestamp(data.get("heartbeat_at"))
    if heartbeat_at is None:
        return {
            "status": "unavailable",
            "message": "runtime heartbeat повреждён",
            "age_seconds": None,
            "run_id": None,
            "heartbeat_at": None,
            "components": {},
            "last_error": None,
        }

    current = (now or datetime.now(UTC)).astimezone(UTC)
    age_seconds = max(0, int((current - heartbeat_at).total_seconds()))
    raw_status = str(data.get("status") or "").lower()
    if raw_status not in _ALLOWED_STATUSES:
        derived_status = "unavailable"
        message = "runtime heartbeat содержит неизвестный статус"
    elif raw_status == "error":
        derived_status = "error"
        message = "runtime завершился с ошибкой"
    elif raw_status == "stopped":
        derived_status = "stopped"
        message = "runtime корректно остановлен"
    elif raw_status == "stopping":
        derived_status = "stopping"
        message = "runtime завершает работу"
    elif age_seconds > max(1, freshness_seconds):
        derived_status = "stale"
        message = "heartbeat runtime устарел; требуется проверка"
    elif raw_status == "starting":
        derived_status = "starting"
        message = "runtime запускается"
    else:
        derived_status = "healthy"
        message = "Telegram runtime подтверждён"

    raw_components = data.get("components")
    components = (
        {str(key): str(value)[:80] for key, value in raw_components.items()}
        if isinstance(raw_components, dict)
        else {}
    )
    return {
        "status": derived_status,
        "message": message,
        "age_seconds": age_seconds,
        "run_id": str(data.get("run_id") or "") or None,
        "started_at": str(data.get("started_at") or "") or None,
        "heartbeat_at": str(data.get("heartbeat_at") or "") or None,
        "components": components,
        "last_error": str(data.get("last_error") or "")[:160] or None,
    }


class RuntimeHeartbeat:
    """Writer for one production process' health record."""

    def __init__(self, path: Path | None = None, *, run_id: str | None = None) -> None:
        self.path = path or runtime_health_path()
        self.run_id = run_id or str(uuid.uuid4())
        self.started_at = utc_timestamp()

    def start(self) -> dict[str, Any]:
        return self._write("starting")

    def beat(self, components: Mapping[str, object]) -> dict[str, Any]:
        normalized = {str(key): str(value)[:80] for key, value in components.items()}
        return self._write("running", components=normalized)

    def stopping(self) -> dict[str, Any]:
        return self._write("stopping")

    def stopped(self) -> dict[str, Any]:
        return self._write("stopped")

    def failed(self, error_type: str) -> dict[str, Any]:
        # Persist only an exception class/category.  Full errors stay in the
        # redacted owner log; a heartbeat must never become a secret carrier.
        return self._write("error", last_error=str(error_type)[:160])

    def _write(
        self,
        status: str,
        *,
        components: Mapping[str, str] | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": RUNTIME_HEALTH_SCHEMA,
            "run_id": self.run_id,
            "status": status,
            "started_at": self.started_at,
            "heartbeat_at": utc_timestamp(),
            "components": dict(components or {}),
            "last_error": last_error,
        }
        _atomic_write_json(self.path, payload)
        return payload


def seconds_until_next_heartbeat(interval_seconds: int) -> float:
    """Expose a clamped interval for callers that read configuration values."""

    return float(max(5, min(int(interval_seconds), 60)))
