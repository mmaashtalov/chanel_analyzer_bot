from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.workspace_intelligence.models import WorkspaceIntelligenceReport


def _text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(title, fontsize=18, fontweight="bold", y=0.96)
    y = 0.91
    for line in lines:
        wrapped = textwrap.wrap(line, width=92) or [""]
        for fragment in wrapped:
            fig.text(0.08, y, fragment, fontsize=10.5, va="top")
            y -= 0.025
        y -= 0.008
        if y < 0.07:
            break
    fig.text(0.08, 0.035, "Telegram Intelligence Platform · Workspace Intelligence v1", fontsize=8)
    plt.axis("off")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_workspace_pdf(report: WorkspaceIntelligenceReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in report.workspace_name)[:60]
    path = output_dir / f"workspace_{safe_name}_{report.generated_at:%Y%m%d_%H%M%S}.pdf"

    with PdfPages(path) as pdf:
        _text_page(pdf, f"Workspace Intelligence: {report.workspace_name}", [
            f"Сформировано: {report.generated_at:%Y-%m-%d %H:%M UTC}",
            f"Покрытие: {report.coverage_status.value} ({report.coverage_ratio:.0%})",
            f"Каналов с профилем: {report.analyzed_channel_count} из {report.requested_channel_count}",
            f"Публикаций в последних профилях: {report.total_posts:,}".replace(",", " "),
            f"Взвешенный confidence: {report.weighted_confidence:.0%}",
            f"Средний охват: {report.mean_views:,.1f}".replace(",", " ") if report.mean_views is not None else "Средний охват: н/д",
            f"Средний ER/1000: {report.mean_engagement_per_1000:.1f}" if report.mean_engagement_per_1000 is not None else "Средний ER/1000: н/д",
            f"Средняя активность: {report.mean_posts_per_day:.1f} постов/сутки" if report.mean_posts_per_day is not None else "Средняя активность: н/д",
            "",
            "Главные выводы:",
            *[f"[{item.severity.upper()}] {item.title}. {item.description} Confidence {item.confidence:.0%}." for item in report.findings[:8]],
        ])

        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Каналы и покрытие", fontsize=18, fontweight="bold", y=0.96)
        if report.channels:
            names = [f"@{item.username}" for item in report.channels]
            posts = [item.posts_count for item in report.channels]
            ax = fig.add_axes([0.15, 0.54, 0.75, 0.32])
            ax.barh(names, posts)
            ax.set_xlabel("Публикаций в последней версии профиля")
            ax.invert_yaxis()
            conf_ax = fig.add_axes([0.15, 0.12, 0.75, 0.30])
            conf_ax.barh(names, [item.confidence * 100 for item in report.channels])
            conf_ax.set_xlim(0, 100)
            conf_ax.set_xlabel("Confidence, %")
            conf_ax.invert_yaxis()
        else:
            fig.text(0.1, 0.8, "Нет сохранённых профилей каналов.", fontsize=13)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        top_lines = ["Сущности:"]
        top_lines.extend(f"• {name}: {count}" for name, count in report.top_entities) or top_lines.append("• нет данных")
        top_lines.append("")
        top_lines.append("Домены:")
        top_lines.extend(f"• {name}: {count}" for name, count in report.top_domains) or top_lines.append("• нет данных")
        top_lines.append("")
        top_lines.append("Ключевые слова:")
        top_lines.extend(f"• {name}: {count}" for name, count in report.top_keywords) or top_lines.append("• нет данных")
        top_lines.append("")
        top_lines.append("Alerts:")
        top_lines.extend(f"• {severity}: {count}" for severity, count in sorted(report.alert_counts.items())) or top_lines.append("• нет событий")
        _text_page(pdf, "Объекты и сигналы Workspace", top_lines)

        methodology = [
            "Методология:",
            "• Используются последние сохранённые версии Intelligence Profile каналов.",
            "• Агрегаты по охватам и вовлечённости взвешиваются количеством публикаций.",
            "• Сущности, домены и события берутся из версионированного Intelligence Graph и Alert Engine.",
            "• Все выводы являются аналитическими сигналами и требуют проверки первичных публикаций.",
            "",
            "Ограничения:",
            *[f"• {item}" for item in report.limitations],
        ]
        _text_page(pdf, "Методология и ограничения", methodology)

    return path
