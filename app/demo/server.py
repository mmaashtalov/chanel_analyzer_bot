from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ASSET_DIR = Path(__file__).resolve().parent / "assets"
DEMO_VERSION = "0.23.0-demo"
REQUIRED_ASSETS = (
    "provenance.json", "provenance.pdf", "verification.json", "verification.pdf",
    "acquisition_request.json", "external_acquisition.json",
    "source_independence.json", "source_independence.pdf",
    "claim_timeline.json", "claim_timeline.pdf",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_self_test() -> dict:
    checks: list[dict] = []
    for name in REQUIRED_ASSETS:
        path = ASSET_DIR / name
        exists = path.is_file() and path.stat().st_size > 0
        checks.append({
            "name": name,
            "status": "ok" if exists else "failed",
            "size": path.stat().st_size if exists else 0,
            "sha256": _sha256(path) if exists else None,
        })
    for name in [x for x in REQUIRED_ASSETS if x.endswith(".json")]:
        try:
            _load_json(name)
            checks.append({"name": f"parse:{name}", "status": "ok"})
        except (OSError, json.JSONDecodeError) as exc:
            checks.append({"name": f"parse:{name}", "status": "failed", "error": str(exc)})
    failed = [item for item in checks if item["status"] != "ok"]
    return {
        "status": "ok" if not failed else "failed",
        "version": DEMO_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
    }


def _load_json(name: str) -> dict:
    with (ASSET_DIR / name).open("r", encoding="utf-8") as source:
        return json.load(source)


def build_summary() -> dict:
    provenance = _load_json("provenance.json")
    independence = _load_json("source_independence.json")
    timeline = _load_json("claim_timeline.json")
    verification = _load_json("verification.json")
    external = _load_json("external_acquisition.json")

    report = provenance.get("report", {})
    prov = provenance.get("provenance", {})
    independence_payload = independence.get("report", independence)
    timeline_payload = timeline.get("report", timeline)
    verification_payload = verification.get("report", verification)

    claims = prov.get("claims", [])
    evidence = prov.get("evidence", [])
    primary_documents = [item for item in evidence if item.get("kind") == "primary_document"]

    return {
        "product": "Telegram Intelligence Platform",
        "release": "Public demo for product v0.23.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "workspace": {
            "id": report.get("workspace_id", "demo-workspace"),
            "name": report.get("workspace_name", "ОПК и БПЛА"),
            "trend": report.get("trend", "escalating"),
            "confidence": report.get("confidence", 0.95),
        },
        "kpis": {
            "claims": len(claims),
            "evidence_references": len(evidence),
            "primary_documents": len(primary_documents),
            "provenance_completeness": prov.get("completeness", 0.6),
            "integrity_hash": prov.get("integrity_hash"),
            "self_test": run_self_test()["status"],
        },
        "observations": report.get("observations", []),
        "claims": claims,
        "primary_documents": primary_documents,
        "independence": independence_payload,
        "timeline": timeline_payload,
        "verification": verification_payload,
        "external_acquisition": external,
        "guided_demo": [
            {"step": 1, "title": "Sources", "result": "Telegram, RSS и Web нормализованы в единую модель документа."},
            {"step": 2, "title": "Workspace Evolution", "result": "Зафиксирован рост объёма публикаций на 55% при confidence 95%."},
            {"step": 3, "title": "Claims & Provenance", "result": "5 claims связаны с 10 evidence references и первичными документами."},
            {"step": 4, "title": "Analyst Verification", "result": "Решение аналитика сохраняется с audit hash и историей статусов."},
            {"step": 5, "title": "Source Independence", "result": "Перепечатки объединяются в lineage-кластеры и не считаются независимыми."},
            {"step": 6, "title": "Claim Timeline", "result": "Утверждения связаны как supports, updates, supersedes и contradicts."},
        ],
        "artifacts": [
            {"title": "Document provenance", "json": "/artifacts/provenance.json", "pdf": "/artifacts/provenance.pdf"},
            {"title": "Analyst verification", "json": "/artifacts/verification.json", "pdf": "/artifacts/verification.pdf"},
            {"title": "Evidence acquisition request", "json": "/artifacts/acquisition_request.json"},
            {"title": "Controlled external acquisition", "json": "/artifacts/external_acquisition.json"},
            {"title": "Source independence", "json": "/artifacts/source_independence.json", "pdf": "/artifacts/source_independence.pdf"},
            {"title": "Temporal claim timeline", "json": "/artifacts/claim_timeline.json", "pdf": "/artifacts/claim_timeline.pdf"},
        ],
    }


HTML = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Telegram Intelligence Platform — Live Demo</title>
<style>
:root{--bg:#07111f;--panel:#0e1b2d;--panel2:#13243a;--text:#edf5ff;--muted:#9fb0c5;--line:#243852;--accent:#55d6be;--warn:#ffbd59;--danger:#ff6b7a}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(circle at 15% 0,#16304e 0,transparent 32%),var(--bg);color:var(--text)}
a{color:var(--accent);text-decoration:none}.wrap{max-width:1180px;margin:auto;padding:24px}.hero{padding:42px 0 22px}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:800}.hero h1{font-size:clamp(34px,7vw,72px);line-height:.96;margin:12px 0 18px;max-width:900px}.hero p{max-width:780px;font-size:18px;line-height:1.6;color:var(--muted)}
.badges{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}.badge{border:1px solid var(--line);background:#0b1727cc;border-radius:999px;padding:8px 12px;font-size:13px}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{background:linear-gradient(145deg,#102038,#0b1728);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 18px 40px #0004}.kpi{grid-column:span 3}.kpi .v{font-size:34px;font-weight:850;margin-top:8px}.kpi .l{color:var(--muted);font-size:13px}.wide{grid-column:span 8}.side{grid-column:span 4}.full{grid-column:1/-1}h2{margin:0 0 14px;font-size:21px}h3{margin:0 0 8px}.muted{color:var(--muted)}
.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.step{padding:15px;border-radius:14px;background:var(--panel2);border:1px solid var(--line);min-height:95px}.step b{display:block;color:var(--accent);font-size:12px;margin-bottom:8px}.obs,.claim,.doc,.artifact{padding:14px 0;border-top:1px solid var(--line)}.obs:first-child,.claim:first-child,.doc:first-child{border-top:0}.sev{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800;text-transform:uppercase}.high{background:#612737;color:#ffd7dd}.medium{background:#594318;color:#ffe3a2}.low{background:#173f42;color:#b7fff5}.bar{height:8px;background:#1b2d43;border-radius:99px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#6fa8ff)}button,.btn{border:0;border-radius:11px;padding:10px 13px;background:var(--accent);color:#03120f;font-weight:800;cursor:pointer;display:inline-block}.btn.secondary{background:#162b43;color:var(--text);border:1px solid var(--line)}.actions{display:flex;flex-wrap:wrap;gap:9px}.hash{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11px;word-break:break-all;background:#07111f;padding:10px;border-radius:10px;color:#b8c8da}.status{display:flex;align-items:center;gap:8px}.dot{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 14px var(--accent)}footer{padding:38px 0;color:var(--muted);font-size:13px}
@media(max-width:850px){.kpi{grid-column:span 6}.wide,.side{grid-column:1/-1}.flow{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.wrap{padding:16px}.kpi{grid-column:1/-1}.flow{grid-template-columns:1fr}.hero{padding-top:25px}}
</style>
</head>
<body><main class="wrap">
<section class="hero"><div class="eyebrow">Evidence-first OSINT · public demonstration</div><h1>Telegram Intelligence Platform</h1><p>Рабочая демонстрация аналитического контура: сбор источников, Workspace Evolution, claims, первичные документы, provenance, верификация аналитиком, дозапрос доказательств, независимость источников и временная история утверждений.</p><div class="badges"><span class="badge status"><i class="dot"></i> Demo service online</span><span class="badge">Product v0.22.0</span><span class="badge">Regression count in manifest</span><span class="badge">No personal Telegram session required</span></div></section>
<section id="kpis" class="grid"></section>
<section class="grid" style="margin-top:16px"><article class="card full"><h2>Сквозной сценарий</h2><div class="flow"><div class="step"><b>01 · Sources</b>Telegram, RSS и Web приводятся к единой модели документа.</div><div class="step"><b>02 · Workspace</b>Источники, ключевые слова, сущности и домены объединяются в контур.</div><div class="step"><b>03 · Evolution</b>Baseline и current snapshots сравниваются без подмены причинностью.</div><div class="step"><b>04 · Provenance</b>Каждый claim связан с расчётами и первичными документами.</div><div class="step"><b>05 · Verification</b>Аналитик подтверждает, отклоняет или запрашивает доказательства.</div><div class="step"><b>06 · Timeline</b>Утверждения связываются как supports, updates, supersedes и contradicts.</div></div><div class="actions" style="margin-top:16px"><button id="startDemo">Запустить пошаговый показ</button><a class="btn secondary" href="/api/self-test" target="_blank">Открыть self-test</a></div><div id="guided" style="margin-top:14px"></div></article>
<article class="card wide"><h2>Наблюдения Workspace</h2><div id="observations"></div></article><aside class="card side"><h2>Проверяемость</h2><p class="muted">Integrity hash меняется при изменении claims, evidence, review или связей.</p><div id="hash" class="hash"></div><div style="height:16px"></div><h3>Доказательная полнота</h3><div id="completenessLabel" class="muted"></div><div class="bar"><i id="completenessBar"></i></div></aside>
<article class="card wide"><h2>Analytic claims</h2><div id="claims"></div></article><aside class="card side"><h2>Первичные документы</h2><div id="docs"></div></aside>
<article class="card full"><h2>Проверяемые артефакты</h2><p class="muted">JSON можно использовать для машинной проверки, PDF — для демонстрации и передачи наблюдателю.</p><div id="artifacts"></div></article></section>
<footer>Демонстрационный набор воспроизводит возможности продукта без доступа к личной Telegram-сессии. Production-mode использует ту же доменную архитектуру и реальные adapters.</footer>
</main>
<script>
const pct=v=>Math.round((Number(v)||0)*100)+'%';
fetch('/api/demo').then(r=>r.json()).then(d=>{
 const k=[['Claims',d.kpis.claims],['Evidence',d.kpis.evidence_references],['Primary documents',d.kpis.primary_documents],['Confidence',pct(d.workspace.confidence)]];
 document.querySelector('#kpis').innerHTML=k.map(x=>`<article class="card kpi"><div class="l">${x[0]}</div><div class="v">${x[1]}</div></article>`).join('');
 document.querySelector('#hash').textContent=d.kpis.integrity_hash||'not available';
 document.querySelector('#completenessLabel').textContent=pct(d.kpis.provenance_completeness);
 document.querySelector('#completenessBar').style.width=pct(d.kpis.provenance_completeness);
 document.querySelector('#observations').innerHTML=(d.observations||[]).map(o=>`<div class="obs"><span class="sev ${o.severity}">${o.severity}</span><h3 style="margin-top:9px">${o.observation}</h3><div class="muted">${o.assessment}</div><div style="margin-top:7px">Confidence: <b>${pct(o.confidence)}</b></div></div>`).join('');
 document.querySelector('#claims').innerHTML=(d.claims||[]).map((c,i)=>`<div class="claim"><div class="muted">Claim ${i+1} · ${c.category}</div><h3>${c.statement}</h3><div>${c.assessment||''}</div><div class="muted" style="margin-top:7px">Confidence ${pct(c.confidence)} · Evidence quality ${pct(c.evidence_quality)}</div></div>`).join('');
 document.querySelector('#docs').innerHTML=(d.primary_documents||[]).map(x=>`<div class="doc"><h3>${x.label}</h3><div class="muted">${x.source_type} · ${x.author||'автор не указан'}</div><p>${x.excerpt||''}</p>${x.canonical_url?`<a href="${x.canonical_url}" target="_blank" rel="noreferrer">Открыть источник ↗</a>`:''}</div>`).join('');
 const guided=d.guided_demo||[]; let guidedIndex=0; document.querySelector('#startDemo').onclick=()=>{ const x=guided[guidedIndex%guided.length]; document.querySelector('#guided').innerHTML=`<div class="step"><b>Шаг ${x.step} · ${x.title}</b>${x.result}</div>`; guidedIndex++; };
 document.querySelector('#artifacts').innerHTML=(d.artifacts||[]).map(a=>`<div class="artifact"><h3>${a.title}</h3><div class="actions"><a class="btn" href="${a.json}" target="_blank">JSON</a>${a.pdf?`<a class="btn secondary" href="${a.pdf}" target="_blank">PDF</a>`:''}</div></div>`).join('');
}).catch(e=>document.body.innerHTML='<pre>Demo data loading failed: '+e+'</pre>');
</script></body></html>'''


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "TelegramIntelligenceDemo/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"demo_http {self.address_string()} {fmt % args}")

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "public, max-age=300")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path in {"/", "/index.html"}:
            self._send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in {"/health", "/api/health"}:
            self_test = run_self_test()
            payload = {"status": self_test["status"], "mode": "demo", "version": DEMO_VERSION, "assets": len(list(ASSET_DIR.iterdir()))}
            status = 200 if self_test["status"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
            self._send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)
            return
        if path in {"/ready", "/api/ready"}:
            self_test = run_self_test()
            status = 200 if self_test["status"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
            self._send_bytes(json.dumps(self_test, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)
            return
        if path == "/api/self-test":
            self_test = run_self_test()
            status = 200 if self_test["status"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
            self._send_bytes(json.dumps(self_test, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8", status)
            return
        if path == "/api/demo":
            self._send_bytes(json.dumps(build_summary(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path.startswith("/artifacts/"):
            name = Path(path.removeprefix("/artifacts/")).name
            candidate = ASSET_DIR / name
            if candidate.exists() and candidate.is_file():
                content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                if content_type == "application/json":
                    content_type += "; charset=utf-8"
                self._send_bytes(candidate.read_bytes(), content_type)
                return
        self._send_bytes(b'{"detail":"not found"}', "application/json", HTTPStatus.NOT_FOUND)


def run_demo_server() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"demo_server_started http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_demo_server()
