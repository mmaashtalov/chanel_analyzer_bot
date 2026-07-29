from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.evidence.review import detect_evidence_gaps


def _page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(title, fontsize=18, fontweight="bold", y=0.96)
    y = 0.91
    for line in lines:
        for fragment in textwrap.wrap(line, width=92) or [""]:
            fig.text(0.08, y, fragment, fontsize=10.2, va="top")
            y -= 0.024
        y -= 0.007
        if y < 0.07:
            break
    fig.text(0.08, 0.035, "Telegram Intelligence Platform · Analyst Verification v1", fontsize=8)
    plt.axis("off")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_verification_exports(bundle: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    subject = str(bundle.get("subject_id", "bundle")).split(":", 1)[0]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in subject)[:60]
    json_path = output_dir / f"verification_{safe}_{stamp}.json"
    pdf_path = output_dir / f"verification_{safe}_{stamp}.pdf"

    json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    gaps = detect_evidence_gaps(bundle)
    claims = list(bundle.get("claims", []))

    with PdfPages(pdf_path) as pdf:
        _page(pdf, "Analyst Verification", [
            f"Subject: {bundle.get('subject_id', 'н/д')}",
            f"Methodology: {bundle.get('methodology_version', 'н/д')}",
            f"Evidence completeness: {float(bundle.get('completeness', 0)):.0%}",
            f"Review completeness: {float(bundle.get('review_completeness', 0)):.0%}",
            f"Claims: {len(claims)}",
            f"Evidence gaps: {len(gaps)}",
            f"Integrity SHA-256: {bundle.get('integrity_hash', 'н/д')}",
        ])
        for offset in range(0, len(claims), 4):
            lines: list[str] = []
            for claim in claims[offset:offset + 4]:
                lines.extend([
                    f"Claim {claim.get('claim_index')}: {claim.get('statement')}",
                    f"ID: {claim.get('claim_id')}",
                    f"Status: {claim.get('review_status', 'unreviewed')}",
                    f"Confidence: {float(claim.get('confidence', 0)):.0%}",
                    f"Evidence quality: {float(claim.get('evidence_quality', 0)):.0%}",
                    f"Source independence: {float(claim.get('independence_score', 0)):.0%}",
                    f"Corroboration: {float(claim.get('corroboration_score', 0)):.0%}",
                    f"Independent clusters: {int((claim.get('corroboration') or {}).get('independent_cluster_count', 0))}",
                    f"Analyst comment: {claim.get('review_comment') or 'нет'}",
                    f"Review version: {claim.get('review_version', 0)}",
                    "",
                ])
            _page(pdf, "Claims и решения аналитика", lines)
        gap_lines = [
            f"[{gap.severity.upper()}] {gap.code} · {gap.claim_id}\n{gap.description}"
            for gap in gaps
        ] or ["Пробелы доказательной базы не выявлены."]
        _page(pdf, "Evidence gaps", gap_lines)
        _page(pdf, "Методология", [
            "Review status является решением аналитика, а не автоматически установленным фактом.",
            "Каждое изменение статуса фиксируется отдельным неизменяемым событием с SHA-256 hash.",
            "После review пересчитываются confidence, evidence quality, review completeness и integrity hash.",
            "Наличие первичного документа не доказывает причинность, координацию или намерение стороны.",
            "Несколько публикаций не считаются независимыми, если совпадают content hash, fingerprint, upstream-домен или текстовая структура.",
        ])
    return json_path, pdf_path
