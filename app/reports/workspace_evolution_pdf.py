from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.workspace_evolution.models import WorkspaceEvolutionReport
from app.evidence.models import ProvenanceBundle


def _page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(title, fontsize=18, fontweight="bold", y=0.96)
    y = 0.91
    for line in lines:
        for fragment in textwrap.wrap(line, width=92) or [""]:
            fig.text(0.08, y, fragment, fontsize=10.3, va="top")
            y -= 0.024
        y -= 0.007
        if y < 0.07:
            break
    fig.text(0.08, 0.035, "Telegram Intelligence Platform · Workspace Evolution v1", fontsize=8)
    plt.axis("off")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _fmt_pct(value) -> str:
    return "н/д" if value is None else f"{value:+.0%}"


def build_workspace_evolution_pdf(
    report: WorkspaceEvolutionReport, output_dir: Path, provenance: ProvenanceBundle | None = None
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in report.workspace_name)[:60]
    path = output_dir / f"workspace_changes_{safe}_{report.current_generated_at:%Y%m%d_%H%M%S}.pdf"
    with PdfPages(path) as pdf:
        _page(pdf, f"Workspace Evolution: {report.workspace_name}", [
            f"Период: {report.baseline_generated_at:%Y-%m-%d %H:%M UTC} → {report.current_generated_at:%Y-%m-%d %H:%M UTC}",
            f"Тренд: {report.trend.value}",
            f"Confidence: {report.confidence:.0%}",
            f"Публикации: {_fmt_pct(report.metric_deltas.get('total_posts_percent'))}",
            f"Охват: {_fmt_pct(report.metric_deltas.get('mean_views_percent'))}",
            f"Активность: {_fmt_pct(report.metric_deltas.get('activity_percent'))}",
            f"Покрытие: {float(report.metric_deltas.get('coverage_ratio') or 0):+.0%}",
            "",
            "Ключевые наблюдения:",
            *[f"[{o.severity.upper()}] {o.observation} Confidence {o.confidence:.0%}. {o.assessment}" for o in report.observations[:10]],
        ])
        object_lines = ["Новые сущности:"]
        object_lines += [f"• {n}: {c}" for n, c in report.added_entities[:15]] or ["• нет"]
        object_lines += ["", "Исчезнувшие сущности:"]
        object_lines += [f"• {n}: {c}" for n, c in report.removed_entities[:15]] or ["• нет"]
        object_lines += ["", "Новые домены:"]
        object_lines += [f"• {n}: {c}" for n, c in report.added_domains[:15]] or ["• нет"]
        object_lines += ["", "Новые темы:"]
        object_lines += [f"• {n}: {c}" for n, c in report.added_keywords[:15]] or ["• нет"]
        _page(pdf, "Изменение объектов и тем", object_lines)
        evidence_lines: list[str] = []
        for index, obs in enumerate(report.observations, 1):
            evidence_lines.extend([
                f"{index}. Observation: {obs.observation}",
                f"Evidence: {'; '.join(obs.evidence) if obs.evidence else 'нет прямых свидетельств'}",
                f"Confidence: {obs.confidence:.0%}",
                f"Assessment: {obs.assessment}", "",
            ])
        _page(pdf, "Evidence и аналитические оценки", evidence_lines or ["Значимых изменений не выявлено."])
        if provenance is not None:
            provenance_lines = [
                f"Bundle ID: {provenance.bundle_id}",
                f"Integrity SHA-256: {provenance.integrity_hash}",
                f"Полнота связей: {provenance.completeness:.0%}",
                f"Утверждений: {len(provenance.claims)}",
                f"Evidence references: {len(provenance.evidence)}",
                "",
            ]
            for claim in provenance.claims[:3]:
                provenance_lines.extend([
                    f"Claim {claim.claim_index}: {claim.statement}",
                    f"Claim ID: {claim.claim_id}",
                    f"Evidence quality: {claim.evidence_quality:.0%}",
                    f"Evidence IDs: {', '.join(claim.evidence_ids)}",
                    "",
                ])
            _page(pdf, "Evidence & Provenance", provenance_lines)
            primary_documents = [item for item in provenance.evidence if item.kind.value == "primary_document"]
            if primary_documents:
                document_lines: list[str] = []
                for item in primary_documents[:12]:
                    document_lines.extend([
                        f"{item.label}",
                        f"Источник: {item.source_type or "н/д"} · {item.author or "автор не указан"}",
                        f"Дата: {item.published_at:%Y-%m-%d %H:%M UTC}" if item.published_at else "Дата: н/д",
                        f"URL/locator: {item.canonical_url or item.locator}",
                        f"Fingerprint: {item.fingerprint or item.content_hash or "н/д"}",
                        f"Фрагмент: {item.excerpt or "нет"}",
                        "",
                    ])
                _page(pdf, "Первичные документы", document_lines)
            if len(provenance.claims) > 3:
                remaining_lines: list[str] = []
                for claim in provenance.claims[3:]:
                    remaining_lines.extend([
                        f"Claim {claim.claim_index}: {claim.statement}",
                        f"Claim ID: {claim.claim_id}",
                        f"Evidence quality: {claim.evidence_quality:.0%}",
                        f"Evidence IDs: {', '.join(claim.evidence_ids)}",
                        f"Caveats: {'; '.join(claim.caveats) if claim.caveats else 'нет'}",
                        "",
                    ])
                _page(pdf, "Evidence & Provenance - продолжение", remaining_lines)
        _page(pdf, "Методология и ограничения", [
            "Сравниваются две последние сохранённые версии Workspace Intelligence Snapshot.",
            "Исходные сообщения повторно не анализируются.",
            "Observation, Evidence, Confidence и Assessment разделены для предотвращения необоснованных выводов.",
            "",
            *[f"• {item}" for item in report.limitations],
            *([] if provenance is None else ["", *[f"• {item}" for item in provenance.limitations]]),
        ])
    return path
