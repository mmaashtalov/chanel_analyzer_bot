from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.96)
    y = 0.91
    for line in lines:
        for fragment in textwrap.wrap(line, width=92) or [""]:
            fig.text(0.08, y, fragment, fontsize=10, va="top")
            y -= 0.024
        y -= 0.006
        if y < 0.06:
            break
    fig.text(0.08, 0.035, "Telegram Intelligence Platform · Temporal Claims v1", fontsize=8)
    plt.axis("off")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_claim_timeline_exports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    workspace = str(report.get("workspace_id", "workspace"))[:50]
    json_path = output_dir / f"claim_timeline_{workspace}_{stamp}.json"
    pdf_path = output_dir / f"claim_timeline_{workspace}_{stamp}.pdf"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with PdfPages(pdf_path) as pdf:
        _page(pdf, "Temporal Claim Tracking", [
            f"Workspace: {report.get('workspace_id')}",
            f"Methodology: {report.get('methodology_version')}",
            f"Claim identities: {report.get('identity_count')}",
            f"Claims: {report.get('claim_count')}",
            f"Relations: {report.get('relation_count')}",
            f"Integrity SHA-256: {report.get('integrity_hash')}",
        ])
        for identity in report.get("identities", []):
            lines = [
                f"Identity: {identity.get('claim_identity_id')}",
                f"Category: {identity.get('category')}",
                f"Canonical statement: {identity.get('canonical_statement')}",
                "",
            ]
            for item in identity.get("timeline", []):
                lines.extend([
                    f"{item.get('generated_at')} · {item.get('temporal_status')}",
                    f"Claim: {item.get('claim_id')}",
                    f"Statement: {item.get('statement')}",
                    f"Relation: {(item.get('relation_from_previous') or {}).get('type', 'origin')}",
                    "",
                ])
            _page(pdf, "Claim timeline", lines)
    return json_path, pdf_path
