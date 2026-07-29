from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.demo.server import ASSET_DIR, HTML as DEMO_HTML, build_summary, run_self_test

CONFIG_DIR = Path(os.getenv("PRODUCT_CONFIG_DIR", "/data/config"))
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "control-center.log"
TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{20,}$")
HASH_RE = re.compile(r"^[A-Fa-f0-9]{16,128}$")

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
    result = {key: config.get(key) for key in PUBLIC_FIELDS if key in config}
    result["telegram_api_id"] = config.get("telegram_api_id")
    for key in SECRET_FIELDS:
        value = str(config.get(key) or "")
        result[f"{key}_configured"] = bool(value)
        result[f"{key}_masked"] = (value[:4] + "…" + value[-4:]) if len(value) >= 10 else ""
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
            api_id = int(merged.get("telegram_api_id"))
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


@dataclass
class ProductManager:
    process: subprocess.Popen[str] | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    events: list[dict[str, Any]] = field(default_factory=list)
    last_exit_code: int | None = None

    def __post_init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.record("control_center_started", "Control Center запущен")

    def record(self, event: str, message: str, **details: Any) -> None:
        entry = {"at": _utc_stamp(), "event": event, "message": message, **details}
        self.events.append(entry)
        self.events[:] = self.events[-100:]
        try:
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def status(self) -> dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is not None:
                self.last_exit_code = self.process.returncode
                self.process = None
            config = load_config()
            return {
                "status": "running" if self.process else "stopped",
                "pid": self.process.pid if self.process else None,
                "last_exit_code": self.last_exit_code,
                "configured": bool(config.get("telegram_bot_token") and config.get("database_url")),
                "config": public_config(config),
                "events": list(reversed(self.events[-20:])),
                "emulator_ready": run_self_test()["status"] == "ok",
                "version": "0.22.0-product",
            }

    def save(self, candidate: dict[str, Any]) -> dict[str, Any]:
        config = validate_config(candidate, load_config())
        _atomic_write(CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2))
        self.record("configuration_saved", "Конфигурация сохранена")
        return public_config(config)

    def migrate(self) -> dict[str, Any]:
        config = validate_config({}, load_config())
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
        if result.returncode != 0:
            self.record("migration_failed", "Миграции завершились ошибкой", exit_code=result.returncode)
            raise RuntimeError(output or "Migration failed")
        self.record("migration_completed", "Миграции применены")
        return {"status": "ok", "output": output}

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is None:
                return self.status()
            config = validate_config({}, load_config())
            self.migrate()
            env = os.environ.copy()
            env.update(config_to_env(config))
            self.process = subprocess.Popen(
                [sys.executable, "-m", "app.entrypoint"],
                cwd=Path.cwd(),
                env=env,
                stdout=LOG_FILE.open("a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            self.last_exit_code = None
            self.record("product_started", "Основной продукт запущен", pid=self.process.pid)
            time.sleep(0.25)
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    self.process.wait(timeout=10)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    self.process.kill()
                self.last_exit_code = self.process.returncode
                self.record("product_stopped", "Основной продукт остановлен", exit_code=self.last_exit_code)
            self.process = None
            return self.status()

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()


MANAGER = ProductManager()

SETUP_HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Telegram Intelligence Control Center</title><style>
:root{--bg:#07111f;--card:#0e1b2d;--line:#21334a;--text:#e9f1fb;--muted:#91a3ba;--accent:#54e1b4;--warn:#ffc857;--bad:#ff6b7a}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#07111f,#0b1730);color:var(--text);font:15px system-ui,sans-serif}.wrap{max-width:1120px;margin:auto;padding:24px}.hero{padding:20px 0 10px}.hero h1{font-size:clamp(28px,6vw,52px);margin:8px 0}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:rgba(14,27,45,.94);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 15px 40px #0004}.full{grid-column:1/-1}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.tab,button,.btn{border:0;border-radius:11px;padding:11px 15px;font-weight:700;cursor:pointer;background:var(--accent);color:#062116;text-decoration:none}.tab.secondary,button.secondary,.btn.secondary{background:#162943;color:var(--text);border:1px solid var(--line)}label{display:block;margin:12px 0 5px;color:#b9c8da}input,select{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:#081522;color:var(--text)}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.status{display:flex;gap:10px;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:var(--bad)}.dot.running{background:var(--accent);box-shadow:0 0 14px var(--accent)}pre{white-space:pre-wrap;background:#06101c;border-radius:12px;padding:12px;max-height:300px;overflow:auto}.hidden{display:none}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}.notice{padding:12px;border-radius:10px;background:#102640;border:1px solid var(--line)}iframe{width:100%;min-height:760px;border:1px solid var(--line);border-radius:14px;background:white}@media(max-width:760px){.grid,.row{grid-template-columns:1fr}.wrap{padding:14px}}
</style></head><body><main class="wrap"><section class="hero"><div class="muted">v0.22.0 · Product Control Center</div><h1>Telegram Intelligence Platform</h1><p class="muted">Введите ключи один раз, примените миграции и запустите продукт. Эмулятор работает отдельно и не требует секретов.</p></section><div class="tabs"><button class="tab" onclick="show('setup')">Настройка</button><button class="tab secondary" onclick="show('emulator')">Эмулятор</button></div>
<section id="setup"><div class="grid"><article class="card"><h2>1. Доступы Telegram</h2><label>Bot Token</label><input id="telegram_bot_token" type="password" placeholder="123456:ABC..."><div class="row"><div><label>API ID</label><input id="telegram_api_id" inputmode="numeric"></div><div><label>API Hash</label><input id="telegram_api_hash" type="password"></div></div><label>String Session (опционально)</label><input id="telegram_string_session" type="password"><div class="notice muted" style="margin-top:12px">Секреты сохраняются только в mounted volume <code>/data/config</code> с правами 0600 и никогда не возвращаются через API.</div></article>
<article class="card"><h2>2. Система</h2><label>PostgreSQL URL</label><input id="database_url"><div class="row"><div><label>Глубина анализа, дней</label><input id="analysis_lookback_days" type="number" value="365"></div><div><label>Максимум постов</label><input id="analysis_max_posts" type="number" value="5000"></div></div><label>Уровень логов</label><select id="log_level"><option>INFO</option><option>DEBUG</option><option>WARNING</option><option>ERROR</option></select><div class="actions"><button onclick="saveConfig()">Сохранить</button><button class="secondary" onclick="migrate()">Применить миграции</button></div></article>
<article class="card full"><div class="status"><i id="dot" class="dot"></i><h2 id="state">Загрузка статуса…</h2></div><div class="actions"><button onclick="action('start')">Запустить</button><button class="secondary" onclick="action('restart')">Перезапустить</button><button class="secondary" onclick="action('stop')">Остановить</button><a class="btn secondary" href="/api/status" target="_blank">JSON-статус</a></div><p id="message" class="muted"></p><pre id="events"></pre></article></div></section>
<section id="emulator" class="hidden"><article class="card"><h2>Интерактивный эмулятор</h2><p class="muted">Показывает полный аналитический workflow на безопасном встроенном наборе данных.</p><iframe src="/emulator"></iframe></article></section></main><script>
const ids=['telegram_bot_token','telegram_api_id','telegram_api_hash','telegram_string_session','database_url','analysis_lookback_days','analysis_max_posts','log_level'];function show(x){document.querySelector('#setup').classList.toggle('hidden',x!=='setup');document.querySelector('#emulator').classList.toggle('hidden',x!=='emulator')}async function api(path,opt={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opt});const j=await r.json();if(!r.ok)throw new Error(j.detail||JSON.stringify(j));return j}async function refresh(){try{const s=await api('/api/status');state.textContent=s.status==='running'?'Продукт работает':'Продукт остановлен';dot.className='dot '+(s.status==='running'?'running':'');events.textContent=(s.events||[]).map(x=>`${x.at} · ${x.message}`).join('\n');const c=s.config||{};for(const id of ['database_url','analysis_lookback_days','analysis_max_posts','log_level','telegram_api_id'])if(c[id]!=null)document.getElementById(id).value=c[id];message.textContent=`Конфигурация: ${s.configured?'готова':'не заполнена'} · Эмулятор: ${s.emulator_ready?'готов':'ошибка'}`}catch(e){message.textContent=e.message}}async function saveConfig(){const body={};for(const id of ids){const el=document.getElementById(id);if(el.value!=='')body[id]=el.type==='number'?Number(el.value):el.value}try{await api('/api/config',{method:'POST',body:JSON.stringify(body)});message.textContent='Конфигурация сохранена';await refresh()}catch(e){message.textContent=e.message}}async function migrate(){try{message.textContent='Применяю миграции…';await api('/api/migrate',{method:'POST',body:'{}'});message.textContent='Миграции применены';await refresh()}catch(e){message.textContent=e.message}}async function action(name){try{message.textContent='Выполняется…';await api('/api/'+name,{method:'POST',body:'{}'});await refresh()}catch(e){message.textContent=e.message}}refresh();setInterval(refresh,5000);
</script></body></html>'''


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "TelegramIntelligenceControlCenter/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"control_http {self.address_string()} {fmt % args}")

    def _send(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
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
        elif path in {"/health", "/api/health"}:
            self._json({"status": "ok", "mode": "setup", "version": "0.22.0-product"})
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
            elif path == "/api/migrate":
                self._json(MANAGER.migrate())
            elif path == "/api/start":
                self._json(MANAGER.start())
            elif path == "/api/stop":
                self._json(MANAGER.stop())
            elif path == "/api/restart":
                self._json(MANAGER.restart())
            else:
                self._json({"detail": "not found"}, 404)
        except ValueError as exc:
            try:
                detail = json.loads(str(exc))
            except json.JSONDecodeError:
                detail = str(exc)
            self._json({"detail": detail}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            self._json({"detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def run_setup_server() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), ControlHandler)
    print(f"control_center_started http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.stop()
        server.server_close()


if __name__ == "__main__":
    run_setup_server()
