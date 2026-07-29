"""Small, dependency-free primitives for phone-first Control Center operations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any

BACKUP_SCHEMA = "telegram-intelligence-mobile-backup-v1"
_TOKEN_RE = re.compile(r"\b\d{5,15}:[A-Za-z0-9_-]{20,}\b")
_DATABASE_PASSWORD_RE = re.compile(
    r"(postgres(?:ql)?(?:\+[^:/@\s]+)?://[^:/@\s]+:)[^@\s]+(@)",
    re.IGNORECASE,
)
_JSON_SECRET_RE = re.compile(
    r'((?:"(?:telegram_bot_token|telegram_api_hash|telegram_string_session|owner_gate_password|password)"\s*:\s*")([^"\\]*)("))',
    re.IGNORECASE,
)


def utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def mask_database_url(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    return _DATABASE_PASSWORD_RE.sub(r"\1***\2", text)


def redact_text(value: object) -> str:
    text = str(value or "")
    text = _TOKEN_RE.sub("[REDACTED_TELEGRAM_TOKEN]", text)
    text = _DATABASE_PASSWORD_RE.sub(r"\1***\2", text)
    text = _JSON_SECRET_RE.sub(lambda match: f'{match.group(1)[:match.group(1).find(":") + 2]}[REDACTED]{match.group(3)}', text)
    return text


def redact_value(value: Any, key: str | None = None) -> Any:
    lowered = (key or "").lower()
    if lowered in {
        "telegram_bot_token",
        "telegram_api_hash",
        "telegram_string_session",
        "owner_gate_password",
        "password",
    }:
        return "[REDACTED]"
    if lowered == "database_url":
        return mask_database_url(value)
    if isinstance(value, dict):
        return {str(item_key): redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def atomic_write_json(path: Path, payload: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, mode)
    temporary.replace(path)
    os.chmod(path, mode)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def load_jsonl_tail(path: Path, limit: int = 100) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    result: list[dict[str, Any]] = []
    for line in lines[-max(limit * 3, limit):]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return result[-limit:]


def read_tail(path: Path, limit: int = 8000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - limit * 2))
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return redact_text(raw)[-limit:]


def process_is_alive(pid: int | None, expected_markers: tuple[str, ...] = ()) -> bool:
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    if not expected_markers:
        return True
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if not proc_cmdline.exists():
        return False
    try:
        command = proc_cmdline.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return False
    return any(marker in command for marker in expected_markers)


def build_backup(
    *,
    product_version: str,
    config: dict[str, Any],
    runtime_state: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": BACKUP_SCHEMA,
        "product_version": product_version,
        "created_at": utc_stamp(),
        "config": config,
        "runtime_state": runtime_state,
        "events": events[-100:],
    }
    return {**body, "integrity_sha256": sha256_payload(body)}


def verify_backup(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != BACKUP_SCHEMA:
        raise ValueError("Неподдерживаемый формат резервной копии")
    supplied = str(payload.get("integrity_sha256") or "")
    body = {key: value for key, value in payload.items() if key != "integrity_sha256"}
    if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(
        supplied, sha256_payload(body)
    ):
        raise ValueError("Резервная копия повреждена: SHA-256 не совпадает")
    if not isinstance(body.get("config"), dict):
        raise TypeError("В резервной копии отсутствует конфигурация")
    return body
