from __future__ import annotations

import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import unquote, urlparse

from app.core.runtime import (
    DEFAULT_FRESHNESS_SECONDS,
    inspect_runtime_health,
    load_runtime_health,
)
from app.demo.server import ASSET_DIR, build_summary, run_self_test
from app.demo.server import HTML as DEMO_HTML
from app.setup.mobile import (
    atomic_write_json,
    build_backup,
    load_json,
    load_jsonl_tail,
    mask_database_url,
    process_is_alive,
    read_tail,
    redact_value,
    utc_stamp,
    verify_backup,
)

PRODUCT_VERSION = "0.24.0-product"

CONFIG_DIR = Path(os.getenv("PRODUCT_CONFIG_DIR", "/data/config"))
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "control-center.log"
RUNTIME_DIR = Path(os.getenv("PRODUCT_RUNTIME_DIR", os.getenv("DATA_DIR", "/data")))
if RUNTIME_DIR.name != "runtime":
    RUNTIME_DIR /= "runtime"
TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{20,}$")
HASH_RE = re.compile(r"^[A-Fa-f0-9]{16,128}$")

RECOVERY_MAX_ATTEMPTS = 3
RECOVERY_WINDOW_SECONDS = 15 * 60
RECOVERY_BACKOFF_SECONDS = (5, 15, 45)

PUBLIC_FIELDS = {
    "app_env",
    "log_level",
    "data_provider",
    "analysis_lookback_days",
    "analysis_max_posts",
    "monitoring_enabled",
    "evidence_acquisition_enabled",
    "database_url",
}
SECRET_FIELDS = {
    "telegram_bot_token",
    "telegram_api_hash",
    "telegram_string_session",
}
ALL_FIELDS = PUBLIC_FIELDS | SECRET_FIELDS | {"telegram_api_id"}


def _utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {
            "app_env": "production",
            "log_level": "INFO",
            "data_provider": "telethon",
            "database_url": os.getenv(
                "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/osint"
            ),
            "analysis_lookback_days": 365,
            "analysis_max_posts": 5000,
            "monitoring_enabled": True,
            "evidence_acquisition_enabled": True,
        }
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return {key: value for key, value in data.items() if key in ALL_FIELDS}
    except (OSError, json.JSONDecodeError):
        return {}


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    result = {key: config.get(key) for key in PUBLIC_FIELDS if key in config and key != "database_url"}
    database_url = str(config.get("database_url") or "")
    result["database_url_configured"] = bool(database_url)
    result["database_url_masked"] = mask_database_url(database_url)
    result["telegram_api_id"] = config.get("telegram_api_id")
    for key in SECRET_FIELDS:
        value = str(config.get(key) or "")
        result[f"{key}_configured"] = bool(value)
    return result


def validate_config(candidate: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    merged = dict(existing)
    for key in ALL_FIELDS:
        if key in candidate and candidate[key] not in {None, ""}:
            merged[key] = candidate[key]

    errors: dict[str, str] = {}
    token = str(merged.get("telegram_bot_token") or "").strip()
    if not TOKEN_RE.match(token):
        errors["telegram_bot_token"] = "Неверный формат Telegram Bot Token"

    provider = str(merged.get("data_provider") or "telethon").strip().lower()
    if provider not in {"telethon", "not_configured"}:
        errors["data_provider"] = "Допустимо: telethon или not_configured"
    merged["data_provider"] = provider

    if provider == "telethon":
        try:
            api_id = int(merged.get("telegram_api_id") or 0)
            if api_id <= 0:
                raise ValueError
            merged["telegram_api_id"] = api_id
        except (TypeError, ValueError):
            errors["telegram_api_id"] = "API ID должен быть положительным числом"
        api_hash = str(merged.get("telegram_api_hash") or "").strip()
        if not HASH_RE.match(api_hash):
            errors["telegram_api_hash"] = "API Hash должен содержать 16–128 hex-символов"
        string_session = str(merged.get("telegram_string_session") or "").strip()
        if len(string_session) < 20:
            errors["telegram_string_session"] = "Нужна Telethon String Session (не менее 20 символов)"

    database_url = str(merged.get("database_url") or "").strip()
    if not database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
        errors["database_url"] = "Нужен PostgreSQL URL"

    for key, default, minimum, maximum in (
        ("analysis_lookback_days", 365, 1, 3650),
        ("analysis_max_posts", 5000, 50, 100000),
    ):
        try:
            value = int(merged.get(key, default))
            if not minimum <= value <= maximum:
                raise ValueError
            merged[key] = value
        except (TypeError, ValueError):
            errors[key] = f"Значение должно быть от {minimum} до {maximum}"

    for key in ("monitoring_enabled", "evidence_acquisition_enabled"):
        value = merged.get(key, True)
        merged[key] = value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "on"}

    merged.setdefault("app_env", "production")
    merged.setdefault("log_level", "INFO")
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    return {key: merged[key] for key in ALL_FIELDS if key in merged}


def config_to_env(config: dict[str, Any]) -> dict[str, str]:
    mapping = {
        "app_env": "APP_ENV",
        "log_level": "LOG_LEVEL",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "database_url": "DATABASE_URL",
        "data_provider": "DATA_PROVIDER",
        "telegram_api_id": "TELEGRAM_API_ID",
        "telegram_api_hash": "TELEGRAM_API_HASH",
        "telegram_string_session": "TELEGRAM_STRING_SESSION",
        "analysis_lookback_days": "ANALYSIS_LOOKBACK_DAYS",
        "analysis_max_posts": "ANALYSIS_MAX_POSTS",
        "monitoring_enabled": "MONITORING_ENABLED",
        "evidence_acquisition_enabled": "EVIDENCE_ACQUISITION_ENABLED",
    }
    env: dict[str, str] = {}
    for key, env_key in mapping.items():
        if key in config and config[key] is not None:
            value = config[key]
            env[env_key] = str(value).lower() if isinstance(value, bool) else str(value)
    env["APP_MODE"] = "production"
    return env


def _runtime_path(name: str) -> Path:
    return CONFIG_FILE.parent / name


def _runtime_health_path() -> Path:
    return RUNTIME_DIR / "runtime-health.json"


def _recovery_default() -> dict[str, Any]:
    return {
        "attempts": [],
        "next_retry_epoch": None,
        "suppressed": False,
        "last_reason": None,
    }


def _state_default() -> dict[str, Any]:
    return {
        "schema": 2,
        "status": "stopped",
        "desired_status": "stopped",
        "pid": None,
        "run_id": None,
        "started_at": None,
        "runtime_deadline_epoch": None,
        "last_exit_code": None,
        "last_error": None,
        "last_operation": None,
        "migration": {"status": "not_run", "at": None, "output": ""},
        "recovery": _recovery_default(),
    }


def _merge_state(payload: Any) -> dict[str, Any]:
    state = _state_default()
    if isinstance(payload, dict):
        state.update({key: value for key, value in payload.items() if key in state})
        migration = payload.get("migration")
        if isinstance(migration, dict):
            state["migration"] = {**state["migration"], **migration}
        recovery = payload.get("recovery")
        if isinstance(recovery, dict):
            state["recovery"] = {**state["recovery"], **recovery}
        if "desired_status" not in payload and state.get("status") in {"running", "degraded"}:
            state["desired_status"] = "running"
    return state


class OperationConflict(RuntimeError):
    """A lifecycle action is unsafe in the current product state."""


@dataclass
class ProductManager:
    process: subprocess.Popen[str] | None = None
    log_handle: TextIO | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    events: list[dict[str, Any]] = field(default_factory=list)
    last_exit_code: int | None = None
    state: dict[str, Any] = field(default_factory=_state_default)
    watchdog_interval_seconds: float = 3.0
    _watchdog_stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _watchdog_thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        global CONFIG_DIR, CONFIG_FILE, LOG_FILE, RUNTIME_DIR
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            fallback_dir = Path(os.getenv("TMPDIR", "/tmp")) / "telegram-intelligence-config"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            CONFIG_DIR = fallback_dir
            CONFIG_FILE = fallback_dir / "settings.json"
            LOG_FILE = fallback_dir / "control-center.log"
            RUNTIME_DIR = fallback_dir.parent / "telegram-intelligence-runtime"
        self.state = _merge_state(load_json(_runtime_path("operation-state.json"), self.state))
        self.events = load_jsonl_tail(LOG_FILE, 100)
        self.last_exit_code = self.state.get("last_exit_code")
        self._reconcile_process()
        self.record("control_center_started", "Control Center запущен")

    def start_watchdog(self) -> None:
        """Start one lightweight supervisor for this Control Center process."""

        with self.lock:
            if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
                return
            self._watchdog_stop.clear()
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="product-runtime-watchdog",
                daemon=True,
            )
            self._watchdog_thread.start()

    def shutdown(self) -> None:
        """Stop the supervisor before the Control Center process exits."""

        self._watchdog_stop.set()
        thread = self._watchdog_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(2.0, self.watchdog_interval_seconds * 2))
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(max(1.0, self.watchdog_interval_seconds)):
            try:
                self.watchdog_tick()
            except Exception as exc:  # noqa: BLE001 - watchdog must survive one failed check
                self.record(
                    "runtime_watchdog_failed",
                    "Watchdog не смог проверить runtime",
                    error_type=type(exc).__name__,
                )

    def _persist_state(self) -> None:
        atomic_write_json(_runtime_path("operation-state.json"), self.state)

    def _record_operation(self, action: str) -> str:
        operation_id = str(uuid.uuid4())
        self.state["last_operation"] = {
            "id": operation_id,
            "action": action,
            "status": "running",
            "started_at": utc_stamp(),
            "finished_at": None,
        }
        self._persist_state()
        return operation_id

    def _finish_operation(self, status: str, error: str | None = None) -> None:
        operation = self.state.get("last_operation")
        if isinstance(operation, dict):
            operation["status"] = status
            operation["finished_at"] = utc_stamp()
            if error:
                operation["error"] = error
        self._persist_state()

    def _runtime_health(self) -> dict[str, Any]:
        return inspect_runtime_health(load_runtime_health(_runtime_health_path()))

    def _recovery(self) -> dict[str, Any]:
        current = self.state.get("recovery")
        if not isinstance(current, dict):
            current = _recovery_default()
            self.state["recovery"] = current
        return current

    def _reset_recovery(self) -> None:
        self.state["recovery"] = _recovery_default()

    def _clear_runtime_health(self) -> None:
        try:
            _runtime_health_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _runtime_requires_attention(self, runtime: dict[str, Any]) -> bool:
        status = runtime.get("status")
        if status in {"stale", "error", "stopping", "stopped"}:
            return True
        if status != "unavailable":
            return False
        deadline = self.state.get("runtime_deadline_epoch")
        try:
            return deadline is not None and time.time() > float(deadline)
        except (TypeError, ValueError):
            return False

    def _mark_live_process(self, pid: int) -> None:
        runtime = self._runtime_health()
        if self._runtime_requires_attention(runtime):
            self.state["status"] = "degraded"
            self.state["last_error"] = str(runtime.get("message") or "Runtime требует проверки")
        else:
            self.state["status"] = "running"
            self.state["last_error"] = None
        self.state["pid"] = pid
        self._persist_state()

    def _record_process_exit(self, return_code: int | None) -> None:
        self.last_exit_code = return_code
        self.state["pid"] = None
        self.state["runtime_deadline_epoch"] = None
        expected_stop = self.state.get("desired_status") != "running"
        self.state["status"] = "stopped" if expected_stop and not return_code else "error"
        self.state["last_exit_code"] = return_code
        if not expected_stop:
            self.state["last_error"] = (
                f"Основной процесс завершился с кодом {return_code}"
                if return_code is not None
                else "Основной процесс завершился неожиданно"
            )
        operation = self.state.get("last_operation")
        if isinstance(operation, dict) and operation.get("status") == "running":
            self._finish_operation(
                "error" if not expected_stop else "success",
                self.state.get("last_error") if not expected_stop else None,
            )
        self._close_log()
        self.process = None
        self._persist_state()

    def _reconcile_process(self) -> None:
        if self.process is not None:
            return_code = self.process.poll()
            if return_code is None:
                self._mark_live_process(self.process.pid)
                return
            self._record_process_exit(return_code)
            return

        pid = self.state.get("pid")
        if pid and process_is_alive(int(pid), ("app.entrypoint", "app.main")):
            self._mark_live_process(int(pid))
            return
        if self.state.get("status") in {"running", "degraded"}:
            self.state["status"] = "error"
            self.state["pid"] = None
            self.state["runtime_deadline_epoch"] = None
            self.state["last_error"] = "Процесс коллектора больше не обнаружен после перезапуска Control Center"
            operation = self.state.get("last_operation")
            if isinstance(operation, dict) and operation.get("status") == "running":
                self._finish_operation("error", self.state["last_error"])
            self._persist_state()

    def _is_running(self) -> bool:
        self._reconcile_process()
        if self.process is not None and self.process.poll() is None:
            return True
        pid = self.state.get("pid")
        return bool(pid and process_is_alive(int(pid), ("app.entrypoint", "app.main")))

    def _schedule_recovery(self, reason: str) -> None:
        """Schedule a bounded retry without blocking the Control Center thread."""

        recovery = self._recovery()
        if recovery.get("suppressed"):
            return
        now = time.time()
        attempts: list[float] = []
        for value in recovery.get("attempts", []):
            try:
                timestamp = float(value)
            except (TypeError, ValueError):
                continue
            if timestamp >= now - RECOVERY_WINDOW_SECONDS:
                attempts.append(timestamp)
        recovery["attempts"] = attempts
        recovery["last_reason"] = reason
        if len(attempts) >= RECOVERY_MAX_ATTEMPTS:
            recovery["suppressed"] = True
            recovery["next_retry_epoch"] = None
            self.state["status"] = "error"
            self.state["last_error"] = (
                "Автовосстановление остановлено: превышен лимит "
                f"{RECOVERY_MAX_ATTEMPTS} попыток за {RECOVERY_WINDOW_SECONDS // 60} мин."
            )
            self._persist_state()
            self.record(
                "auto_recovery_suppressed",
                "Автовосстановление остановлено защитой от crash-loop",
                attempts=len(attempts),
            )
            return
        delay = RECOVERY_BACKOFF_SECONDS[min(len(attempts), len(RECOVERY_BACKOFF_SECONDS) - 1)]
        recovery["next_retry_epoch"] = now + delay
        self._persist_state()
        self.record(
            "auto_recovery_scheduled",
            "Запланировано автоматическое восстановление продукта",
            delay_seconds=delay,
            reason=reason,
            attempt=len(attempts) + 1,
        )

    def _launch_product(self, config: dict[str, Any], operation_id: str, *, recovered: bool) -> None:
        env = os.environ.copy()
        env.update(config_to_env(config))
        self._clear_runtime_health()
        try:
            self.log_handle = LOG_FILE.open("a", encoding="utf-8")
            self.process = subprocess.Popen(
                [sys.executable, "-m", "app.entrypoint"],
                cwd=Path.cwd(),
                env=env,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except Exception as exc:
            error = f"Не удалось запустить основной процесс: {type(exc).__name__}"
            self._close_log()
            self.process = None
            self.state.update(
                {
                    "status": "error",
                    "pid": None,
                    "last_error": error,
                    "runtime_deadline_epoch": None,
                }
            )
            self._finish_operation("error", error)
            self.record(
                "product_start_failed",
                "Не удалось запустить основной продукт",
                operation_id=operation_id,
                error_type=type(exc).__name__,
            )
            if recovered:
                self._schedule_recovery(error)
            raise

        self.last_exit_code = None
        self.state.update(
            {
                "status": "running",
                "desired_status": "running",
                "pid": self.process.pid,
                "run_id": operation_id,
                "started_at": utc_stamp(),
                "runtime_deadline_epoch": time.time() + DEFAULT_FRESHNESS_SECONDS,
                "last_exit_code": None,
                "last_error": None,
            }
        )
        self._persist_state()
        self._finish_operation("success")
        self.record(
            "product_auto_recovered" if recovered else "product_started",
            "Основной продукт автоматически перезапущен" if recovered else "Основной продукт запущен",
            pid=self.process.pid,
            operation_id=operation_id,
        )

    def _attempt_recovery(self) -> None:
        recovery = self._recovery()
        recovery["next_retry_epoch"] = None
        attempts = list(recovery.get("attempts", []))
        attempts.append(time.time())
        recovery["attempts"] = attempts[-RECOVERY_MAX_ATTEMPTS:]
        self._persist_state()
        operation_id = self._record_operation("auto_recovery")
        try:
            config = validate_config({}, load_config())
        except Exception as exc:  # noqa: BLE001 - invalid persisted config is a recoverable runtime fault
            error = f"Автовосстановление не выполнилось: {type(exc).__name__}"
            self.state.update({"status": "error", "last_error": error})
            self._finish_operation("error", error)
            self.record(
                "auto_recovery_start_failed",
                "Автовосстановление не смогло подготовить конфигурацию",
                operation_id=operation_id,
                error_type=type(exc).__name__,
            )
            self._schedule_recovery(error)
            return
        try:
            self._launch_product(config, operation_id, recovered=True)
        except Exception:  # noqa: BLE001 - _launch_product records a safe failure and next retry
            # _launch_product stores a safe error and schedules the next retry.
            return

    def watchdog_tick(self) -> None:
        """Reconcile state and recover only unexpected exits within a safe budget."""

        with self.lock:
            self._reconcile_process()
            if self.state.get("desired_status") != "running" or self._is_running():
                return
            recovery = self._recovery()
            if recovery.get("suppressed"):
                return
            next_retry = recovery.get("next_retry_epoch")
            try:
                retry_due = next_retry is not None and float(next_retry) <= time.time()
            except (TypeError, ValueError):
                retry_due = False
            if next_retry is None:
                self._schedule_recovery(str(self.state.get("last_error") or "runtime недоступен"))
            elif retry_due:
                self._attempt_recovery()

    def _close_log(self) -> None:
        if self.log_handle is not None:
            try:
                self.log_handle.close()
            except OSError:
                pass
            self.log_handle = None

    def record(self, event: str, message: str, **details: Any) -> None:
        safe_details = {key: redact_value(value, key) for key, value in details.items()}
        entry = {"at": _utc_stamp(), "event": event, "message": message, **safe_details}
        self.events.append(entry)
        self.events[:] = self.events[-100:]
        try:
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def credential_check(self, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = load_config()
        for key, value in (candidate or {}).items():
            if key in ALL_FIELDS and value is not None and value != "":
                merged[key] = value

        checks: dict[str, dict[str, str]] = {}
        errors: dict[str, str] = {}

        token = str(merged.get("telegram_bot_token") or "").strip()
        checks["telegram_bot_token"] = {
            "status": "ok" if TOKEN_RE.match(token) else "error",
            "message": "формат распознан" if TOKEN_RE.match(token) else "нужен Bot Token формата 123456:ABC…",
        }
        if not TOKEN_RE.match(token):
            errors["telegram_bot_token"] = "Неверный формат Telegram Bot Token"

        provider = str(merged.get("data_provider") or "telethon").strip().lower()
        checks["data_provider"] = {
            "status": "ok" if provider in {"telethon", "not_configured"} else "error",
            "message": provider if provider in {"telethon", "not_configured"} else "допустимо telethon или not_configured",
        }
        if provider not in {"telethon", "not_configured"}:
            errors["data_provider"] = "Допустимо: telethon или not_configured"

        if provider == "telethon":
            try:
                api_id = int(merged.get("telegram_api_id") or 0)
                api_id_ok = api_id > 0
            except (TypeError, ValueError):
                api_id_ok = False
            checks["telegram_api_id"] = {
                "status": "ok" if api_id_ok else "error",
                "message": "положительное число" if api_id_ok else "нужен положительный API ID",
            }
            if not api_id_ok:
                errors["telegram_api_id"] = "API ID должен быть положительным числом"

            api_hash = str(merged.get("telegram_api_hash") or "").strip()
            hash_ok = bool(HASH_RE.match(api_hash))
            checks["telegram_api_hash"] = {
                "status": "ok" if hash_ok else "error",
                "message": "hex-формат распознан" if hash_ok else "нужен API Hash из 16–128 hex-символов",
            }
            if not hash_ok:
                errors["telegram_api_hash"] = "API Hash должен содержать 16–128 hex-символов"

            string_session = str(merged.get("telegram_string_session") or "").strip()
            session_ok = len(string_session) >= 20
            checks["telegram_string_session"] = {
                "status": "ok" if session_ok else "error",
                "message": "String Session задана" if session_ok else "нужна Telethon String Session",
            }
            if not session_ok:
                errors["telegram_string_session"] = "Нужна Telethon String Session (не менее 20 символов)"

        database_url = str(merged.get("database_url") or "").strip()
        database_ok = database_url.startswith(("postgresql+asyncpg://", "postgresql://"))
        checks["database_url"] = {
            "status": "ok" if database_ok else "error",
            "message": "PostgreSQL URL распознан" if database_ok else "нужен postgresql:// или postgresql+asyncpg://",
        }
        if not database_ok:
            errors["database_url"] = "Нужен PostgreSQL URL"

        return {
            "status": "ok" if not errors else "error",
            "checks": checks,
            "errors": errors,
            "message": "Конфигурация готова к запуску" if not errors else "Исправьте отмеченные поля",
        }

    def status(self) -> dict[str, Any]:
        with self.lock:
            self._reconcile_process()
            config = load_config()
            credentials = self.credential_check(config)
            process_status = self.state.get("status", "stopped")
            runtime = self._runtime_health()
            recovery = self._recovery()
            recovery_attempts = [
                value for value in recovery.get("attempts", []) if isinstance(value, (int, float))
            ]
            return {
                "status": process_status,
                "pid": self.state.get("pid"),
                "last_exit_code": self.last_exit_code,
                "last_error": self.state.get("last_error"),
                "configured": credentials["status"] == "ok",
                "config": public_config(config),
                "configuration": credentials,
                "migration": self.state.get("migration"),
                "operation": self.state.get("last_operation"),
                "runtime": runtime,
                "recovery": {
                    "desired_status": self.state.get("desired_status", "stopped"),
                    "attempt_count": len(recovery_attempts),
                    "max_attempts": RECOVERY_MAX_ATTEMPTS,
                    "window_seconds": RECOVERY_WINDOW_SECONDS,
                    "next_retry_epoch": recovery.get("next_retry_epoch"),
                    "suppressed": bool(recovery.get("suppressed")),
                    "last_reason": recovery.get("last_reason"),
                },
                "collector": {
                    "status": process_status,
                    "desired_status": self.state.get("desired_status", "stopped"),
                    "pid": self.state.get("pid"),
                    "last_error": self.state.get("last_error"),
                    "started_at": self.state.get("started_at"),
                },
                "events": list(reversed(self.events[-20:])),
                "emulator_ready": run_self_test()["status"] == "ok",
                "version": PRODUCT_VERSION,
            }

    def save(self, candidate: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self._is_running():
                raise OperationConflict("Сначала остановите продукт, затем изменяйте конфигурацию")
            config = validate_config(candidate, load_config())
            _atomic_write(CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2))
            self.state["migration"] = {"status": "pending", "at": None, "output": ""}
            self.state["last_error"] = None
            self._persist_state()
            self.record("configuration_saved", "Конфигурация сохранена")
            return public_config(config)

    def migrate(self) -> dict[str, Any]:
        with self.lock:
            if self._is_running():
                raise OperationConflict("Сначала остановите продукт перед применением миграций")
            config = validate_config({}, load_config())
            operation_id = self._record_operation("migrate")
            env = os.environ.copy()
            env.update(config_to_env(config))
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=Path.cwd(),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            output = (result.stdout + "\n" + result.stderr).strip()[-8000:]
            safe_output = redact_value(output)
            if result.returncode != 0:
                error = safe_output or "Миграции завершились ошибкой"
                self.state["migration"] = {"status": "error", "at": utc_stamp(), "output": error}
                self.state["last_error"] = error
                self._finish_operation("error", error)
                self.record("migration_failed", "Миграции завершились ошибкой", operation_id=operation_id, exit_code=result.returncode)
                raise RuntimeError(error)
            self.state["migration"] = {"status": "applied", "at": utc_stamp(), "output": safe_output}
            self.state["last_error"] = None
            self._finish_operation("success")
            self.record("migration_completed", "Миграции применены", operation_id=operation_id)
            return {"status": "ok", "operation_id": operation_id, "output": safe_output}

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self._is_running():
                return self.status()
            config = validate_config({}, load_config())
            self.migrate()
            self._reset_recovery()
            self.state["desired_status"] = "running"
            operation_id = self._record_operation("start")
            self._launch_product(config, operation_id, recovered=False)
            time.sleep(0.25)
            return self.status()

    def _terminate_active_process(self) -> None:
        pid = self.process.pid if self.process is not None else self.state.get("pid")
        if not pid:
            return
        pid = int(pid)
        if self.process is None and not process_is_alive(pid, ("app.entrypoint", "app.main")):
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.state["desired_status"] = "stopped"
            self._reset_recovery()
            self._persist_state()
            was_running = self._is_running()
            operation_id = self._record_operation("stop")
            if was_running:
                self._terminate_active_process()
            self.last_exit_code = self.process.returncode if self.process is not None else self.state.get("last_exit_code")
            self._close_log()
            self.process = None
            self.state.update(
                {
                    "status": "stopped",
                    "pid": None,
                    "run_id": None,
                    "runtime_deadline_epoch": None,
                    "last_exit_code": self.last_exit_code,
                    "last_error": None,
                }
            )
            self._finish_operation("success")
            if was_running:
                self.record("product_stopped", "Основной продукт остановлен", operation_id=operation_id, exit_code=self.last_exit_code)
            return self.status()

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()

    def _create_backup(self) -> tuple[bytes, Path, dict[str, Any]]:
        self._reconcile_process()
        payload = build_backup(
            product_version=PRODUCT_VERSION,
            config=load_config(),
            runtime_state=redact_value(self.state),
            events=self.events,
        )
        content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        backup_dir = _runtime_path("backups")
        backup_path = backup_dir / (
            f"telegram-intelligence-backup-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-"
            f"{uuid.uuid4().hex[:8]}.json"
        )
        atomic_write_json(backup_path, payload)
        return content, backup_path, payload

    def backup_download(self) -> tuple[bytes, str, str]:
        with self.lock:
            content, path, payload = self._create_backup()
            self.record("backup_created", "Резервная копия создана", sha256=payload["integrity_sha256"])
            return content, path.name, str(payload["integrity_sha256"])

    def restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self._is_running():
                raise OperationConflict("Сначала остановите продукт перед восстановлением")
            body = verify_backup(payload.get("backup", payload))
            restored_config = validate_config(body["config"], {})
            _atomic_write(CONFIG_FILE, json.dumps(restored_config, ensure_ascii=False, indent=2))
            self.state = _state_default()
            self.state["migration"]["status"] = "pending"
            self._persist_state()
            self.record("backup_restored", "Конфигурация восстановлена из резервной копии")
            return {"status": "ok", "config": public_config(restored_config), "message": "Восстановление завершено; примените миграции и запустите продукт"}

    def diagnostics(self) -> dict[str, Any]:
        with self.lock:
            status = self.status()
            credentials = status["configuration"]
            storage_ok = CONFIG_FILE.parent.exists() and os.access(CONFIG_FILE.parent, os.W_OK)
            emulator = run_self_test()
            runtime = status["runtime"]
            runtime_ok = runtime["status"] in {"healthy", "stopped"} or (
                status["status"] == "stopped" and runtime["status"] == "unavailable"
            )
            recovery = status["recovery"]
            recovery_status = (
                "error" if recovery["suppressed"]
                else "attention" if recovery["next_retry_epoch"] is not None
                else "ok"
            )
            checks = {
                "configuration": {"status": credentials["status"], "message": credentials["message"]},
                "control_center_storage": {"status": "ok" if storage_ok else "error", "message": "volume доступен" if storage_ok else "нет записи в /data"},
                "emulator": {"status": emulator["status"], "message": "demo-артефакты проверены" if emulator["status"] == "ok" else "demo-артефакты требуют проверки"},
                "migration": {"status": status["migration"].get("status", "not_run"), "message": "последняя миграция применена" if status["migration"].get("status") == "applied" else "миграции ещё не подтверждены"},
                "collector": {"status": status["status"], "message": status["last_error"] or "состояние процесса определено"},
                "runtime": {
                    "status": "ok" if runtime_ok else "attention",
                    "message": runtime["message"],
                },
                "auto_recovery": {
                    "status": recovery_status,
                    "message": (
                        "Защита от crash-loop активирована; требуется ручной запуск"
                        if recovery["suppressed"]
                        else "Запланирована попытка автоматического восстановления"
                        if recovery["next_retry_epoch"] is not None
                        else "Автовосстановление готово"
                    ),
                },
            }
            failed = [key for key, value in checks.items() if value["status"] != "ok"]
            recent_errors = [
                item for item in self.events
                if "fail" in str(item.get("event", "")).lower() or "error" in str(item.get("event", "")).lower()
            ][-20:]
            return {
                "status": "ok" if not failed else "attention",
                "checks": checks,
                "failed_checks": failed,
                "recent_errors": recent_errors,
                "log_tail": read_tail(LOG_FILE),
                "version": PRODUCT_VERSION,
            }

    def update_check(self) -> dict[str, Any]:
        current = self.status()
        backup_files = list(_runtime_path("backups").glob("*.json")) if _runtime_path("backups").exists() else []
        running = current["status"] in {"running", "degraded"}
        return {
            "status": "ok",
            "version": PRODUCT_VERSION,
            "python": platform.python_version(),
            "source_revision": os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA") or "не задан",
            "safe_to_prepare": not running,
            "running": running,
            "runtime_status": current["runtime"]["status"],
            "backup_count": len(backup_files),
            "message": "Можно подготовить безопасное обновление" if not running else "Перед обновлением остановите продукт",
        }

    def prepare_update(self) -> dict[str, Any]:
        with self.lock:
            content, path, payload = self._create_backup()
            del content
            if self._is_running():
                self.stop()
            self.record("update_prepared", "Обновление подготовлено: backup создан, продукт остановлен", sha256=payload["integrity_sha256"])
            return {
                "status": "ready",
                "backup_file": path.name,
                "backup_sha256": payload["integrity_sha256"],
                "requires_redeploy": True,
                "message": "Backup создан. Теперь выполните Redeploy/Deploy в используемом хостинге; после обновления примените миграции и запустите продукт.",
            }


MANAGER = ProductManager()

SETUP_HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Telegram Intelligence Control Center</title><style>
:root{--bg:#07111f;--card:#0e1b2d;--line:#21334a;--text:#e9f1fb;--muted:#91a3ba;--accent:#54e1b4;--warn:#ffc857;--bad:#ff6b7a}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#07111f,#0b1730);color:var(--text);font:15px system-ui,sans-serif}.wrap{max-width:1120px;margin:auto;padding:24px}.hero{padding:20px 0 10px}.hero h1{font-size:clamp(28px,6vw,52px);margin:8px 0}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:rgba(14,27,45,.94);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 15px 40px #0004}.full{grid-column:1/-1}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.tab,button,.btn{border:0;border-radius:11px;padding:11px 15px;font-weight:700;cursor:pointer;background:var(--accent);color:#062116;text-decoration:none}.tab.secondary,button.secondary,.btn.secondary{background:#162943;color:var(--text);border:1px solid var(--line)}label{display:block;margin:12px 0 5px;color:#b9c8da}input,select{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:#081522;color:var(--text)}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.status{display:flex;gap:10px;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:var(--bad)}.dot.running{background:var(--accent);box-shadow:0 0 14px var(--accent)}pre{white-space:pre-wrap;background:#06101c;border-radius:12px;padding:12px;max-height:300px;overflow:auto}.hidden{display:none}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}.notice{padding:12px;border-radius:10px;background:#102640;border:1px solid var(--line)}iframe{width:100%;min-height:760px;border:1px solid var(--line);border-radius:14px;background:white}@media(max-width:760px){.grid,.row{grid-template-columns:1fr}.wrap{padding:14px}}
</style></head><body><main class="wrap"><section class="hero"><div class="muted">v0.24.0 · Product Control Center</div><h1>Telegram Intelligence Platform</h1><p class="muted">Введите ключи один раз, примените миграции и запустите продукт. Эмулятор работает отдельно и не требует секретов.</p></section><div class="tabs"><button class="tab" onclick="show('setup')">Настройка</button><button class="tab secondary" onclick="show('emulator')">Эмулятор</button></div>
<section id="setup"><div class="grid"><article class="card"><h2>1. Доступы Telegram</h2><label>Bot Token</label><input id="telegram_bot_token" type="password" placeholder="123456:ABC..."><div class="row"><div><label>API ID</label><input id="telegram_api_id" inputmode="numeric"></div><div><label>API Hash</label><input id="telegram_api_hash" type="password"></div></div><label>String Session (опционально)</label><input id="telegram_string_session" type="password"><div class="notice muted" style="margin-top:12px">Секреты сохраняются только в mounted volume <code>/data/config</code> с правами 0600 и никогда не возвращаются через API.</div></article>
<article class="card"><h2>2. Система</h2><label>PostgreSQL URL</label><input id="database_url"><div class="row"><div><label>Глубина анализа, дней</label><input id="analysis_lookback_days" type="number" value="365"></div><div><label>Максимум постов</label><input id="analysis_max_posts" type="number" value="5000"></div></div><label>Уровень логов</label><select id="log_level"><option>INFO</option><option>DEBUG</option><option>WARNING</option><option>ERROR</option></select><div class="actions"><button onclick="saveConfig()">Сохранить</button><button class="secondary" onclick="migrate()">Применить миграции</button></div></article>
<article class="card full"><div class="status"><i id="dot" class="dot"></i><h2 id="state">Загрузка статуса…</h2></div><div class="actions"><button onclick="action('start')">Запустить</button><button class="secondary" onclick="action('restart')">Перезапустить</button><button class="secondary" onclick="action('stop')">Остановить</button><a class="btn secondary" href="/api/status" target="_blank">JSON-статус</a></div><p id="message" class="muted"></p><pre id="events"></pre></article></div></section>
<section id="emulator" class="hidden"><article class="card"><h2>Интерактивный эмулятор</h2><p class="muted">Показывает полный аналитический workflow на безопасном встроенном наборе данных.</p><iframe src="/emulator"></iframe></article></section></main><script>
const ids=['telegram_bot_token','telegram_api_id','telegram_api_hash','telegram_string_session','database_url','analysis_lookback_days','analysis_max_posts','log_level'];function show(x){document.querySelector('#setup').classList.toggle('hidden',x!=='setup');document.querySelector('#emulator').classList.toggle('hidden',x!=='emulator')}async function api(path,opt={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opt});const j=await r.json();if(!r.ok)throw new Error(j.detail||JSON.stringify(j));return j}async function refresh(){try{const s=await api('/api/status');state.textContent=s.status==='running'?'Продукт работает':'Продукт остановлен';dot.className='dot '+(s.status==='running'?'running':'');events.textContent=(s.events||[]).map(x=>`${x.at} · ${x.message}`).join('\n');const c=s.config||{};for(const id of ['database_url','analysis_lookback_days','analysis_max_posts','log_level','telegram_api_id'])if(c[id]!=null)document.getElementById(id).value=c[id];message.textContent=`Конфигурация: ${s.configured?'готова':'не заполнена'} · Эмулятор: ${s.emulator_ready?'готов':'ошибка'}`}catch(e){message.textContent=e.message}}async function saveConfig(){const body={};for(const id of ids){const el=document.getElementById(id);if(el.value!=='')body[id]=el.type==='number'?Number(el.value):el.value}try{await api('/api/config',{method:'POST',body:JSON.stringify(body)});message.textContent='Конфигурация сохранена';await refresh()}catch(e){message.textContent=e.message}}async function migrate(){try{message.textContent='Применяю миграции…';await api('/api/migrate',{method:'POST',body:'{}'});message.textContent='Миграции применены';await refresh()}catch(e){message.textContent=e.message}}async function action(name){try{message.textContent='Выполняется…';await api('/api/'+name,{method:'POST',body:'{}'});await refresh()}catch(e){message.textContent=e.message}}refresh();setInterval(refresh,5000);
</script></body></html>'''

SETUP_HTML_PATH = Path(__file__).with_name("control_center.html")
if SETUP_HTML_PATH.is_file():
    SETUP_HTML = SETUP_HTML_PATH.read_text(encoding="utf-8")


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "TelegramIntelligenceControlCenter/0.24.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"control_http {self.address_string()} {fmt % args}")

    def _send(
        self,
        payload: bytes,
        content_type: str,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(json.dumps(data, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8", status)

    def _body(self) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0") or 0), 200_000)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Некорректный JSON")

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path in {"/", "/index.html"}:
            self._send(SETUP_HTML.encode(), "text/html; charset=utf-8")
        elif path == "/emulator":
            html = DEMO_HTML.replace("fetch('/api/demo')", "fetch('/api/demo')")
            self._send(html.encode(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(MANAGER.status())
        elif path == "/api/diagnostics":
            result = MANAGER.diagnostics()
            self._json(result)
        elif path == "/api/errors":
            result = MANAGER.diagnostics()
            self._json({"status": result["status"], "recent_errors": result["recent_errors"], "log_tail": result["log_tail"]})
        elif path == "/api/update-check":
            self._json(MANAGER.update_check())
        elif path == "/api/backup":
            payload, filename, digest = MANAGER.backup_download()
            self._send(
                payload,
                "application/json; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Backup-SHA256": digest,
                },
            )
        elif path in {"/health", "/api/health"}:
            self._json({"status": "ok", "mode": "setup", "version": PRODUCT_VERSION})
        elif path in {"/ready", "/api/ready", "/api/self-test"}:
            test = run_self_test()
            self._json(test, 200 if test["status"] == "ok" else 503)
        elif path == "/api/demo":
            self._json(build_summary())
        elif path.startswith("/artifacts/"):
            candidate = ASSET_DIR / Path(path).name
            if candidate.exists() and candidate.is_file():
                ctype = "application/pdf" if candidate.suffix == ".pdf" else "application/json; charset=utf-8"
                self._send(candidate.read_bytes(), ctype)
            else:
                self._json({"detail": "not found"}, 404)
        else:
            self._json({"detail": "not found"}, 404)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            body = self._body()
            if path == "/api/config":
                self._json({"status": "ok", "config": MANAGER.save(body)})
            elif path == "/api/credentials/check":
                result = MANAGER.credential_check(body)
                self._json(result)
            elif path == "/api/migrate":
                self._json(MANAGER.migrate())
            elif path == "/api/start":
                self._json(MANAGER.start())
            elif path == "/api/stop":
                self._json(MANAGER.stop())
            elif path == "/api/restart":
                self._json(MANAGER.restart())
            elif path == "/api/restore":
                self._json(MANAGER.restore(body))
            elif path == "/api/update/prepare":
                self._json(MANAGER.prepare_update())
            else:
                self._json({"detail": "not found"}, 404)
        except (ValueError, TypeError) as exc:
            try:
                detail = json.loads(str(exc))
            except json.JSONDecodeError:
                detail = str(exc)
            self._json({"detail": detail}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except OperationConflict as exc:
            self._json({"detail": str(exc)}, HTTPStatus.CONFLICT)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            self._json({"detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def run_setup_server() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), ControlHandler)
    MANAGER.start_watchdog()
    print(f"control_center_started http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.shutdown()
        MANAGER.stop()
        server.server_close()


if __name__ == "__main__":
    run_setup_server()
