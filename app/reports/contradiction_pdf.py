from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    figure = plt.figure(figsize=(8.27, 11.69))
    figure.suptitle(title, fontsize=17, fontweight="bold", y=0.96)
    y = 0.91
    for line in lines:
        for fragment in textwrap.wrap(str(line), width=92) or [""]:
            figure.text(0.08, y, fragment, fontsize=10, va="top")
            y -= 0.024
        y -= 0.006
        if y < 0.06:
            break
    figure.text(0.08, 0.035, "Telegram Intelligence Platform · Contradiction Resolution v1", fontsize=8)
    plt.axis("off")
    pdf.savefig(figure, bbox_inches="tight")
    plt.close(figure)


def build_contradiction_exports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    workspace = str(report.get("workspace_id", "workspace"))[:50]
    json_path = output_dir / f"contradictions_{workspace}_{stamp}.json"
    pdf_path = output_dir / f"contradictions_{workspace}_{stamp}.pdf"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with PdfPages(pdf_path) as pdf:
        _page(pdf, "Contradiction Dossier", [
            f"Workspace: {report.get('workspace_id')}",
            f"Status filter: {report.get('status_filter')}",
            f"Contradictions: {report.get('contradiction_count')}",
            f"Unresolved: {report.get('unresolved_count')}",
            f"Integrity SHA-256: {report.get('integrity_hash')}",
        ])
        for item in report.get("contradictions", []):
            lines = [
                f"ID: {item.get('contradiction_id')}",
                f"Severity: {item.get('severity')} · confidence {float(item.get('confidence', 0)):.0%}",
                f"Triage priority: {item.get('triage_priority')}",
                f"Status: {item.get('status')}",
                f"Source ({item.get('source_generated_at')}): {item.get('source_statement')}",
                f"Target ({item.get('target_generated_at')}): {item.get('target_statement')}",
                f"Rationale: {'; '.join(item.get('rationale') or [])}",
                f"Resolution: {item.get('resolution_action') or 'not decided'}",
                f"Selected claim: {item.get('selected_claim_id') or 'not selected'}",
                f"Comment: {item.get('resolution_comment') or '—'}",
                "",
            ]
            for event in item.get("history", []):
                lines.append(
                    f"Event {event.get('created_at')}: {event.get('previous_status') or 'new'} "
                    f"→ {event.get('new_status')} · {event.get('action')} · "
                    f"hash {str(event.get('event_hash', ''))[:16]}…"
                )
            _page(pdf, "Contradiction review", lines)
    return json_path, pdf_path
