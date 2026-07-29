from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.domain.models import ChannelSnapshot
from app.similarity import SimilarityResult


def _page(title: str):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=20, fontweight="bold", x=0.06, ha="left")
    return fig


def build_comparison_pdf(a: ChannelSnapshot, b: ChannelSnapshot, result: SimilarityResult, output_dir: Path, job_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"compare_{a.username}_{b.username}_{job_id}.pdf"
    labels = ["Стиль", "Тематика", "Время", "Структура", "Итого"]
    values = [result.style_score, result.narrative_score, result.temporal_score, result.structural_score, result.overall_score]
    with PdfPages(path) as pdf:
        fig = _page(f"Сравнение @{a.username} и @{b.username}")
        fig.text(0.07, 0.80, f"{a.title}\nПостов: {len(a.posts)}\n\n{b.title}\nПостов: {len(b.posts)}", fontsize=14, va="top")
        fig.text(0.07, 0.38, f"Общий индекс сходства: {result.overall_score:.0%}\nConfidence: {result.confidence:.0%}", fontsize=18, fontweight="bold")
        fig.text(0.07, 0.10, f"Сформировано: {datetime.now():%d.%m.%Y %H:%M}\nСходство не является доказательством общего автора.", fontsize=9)
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        fig = _page("Разложение сходства")
        ax = fig.add_axes([0.12, 0.18, 0.76, 0.62])
        ax.bar(labels, values)
        ax.set_ylim(0, 1)
        ax.set_ylabel("Similarity score")
        for index, value in enumerate(values):
            ax.text(index, value + 0.025, f"{value:.0%}", ha="center")
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        fig = _page("Аналитическое объяснение")
        fig.text(0.08, 0.82, result.explanation, fontsize=14, va="top", wrap=True)
        y = 0.55
        fig.text(0.08, y, "Альтернативные объяснения", fontsize=14, fontweight="bold")
        y -= 0.08
        for item in result.alternative_explanations:
            fig.text(0.08, y, "• " + item, fontsize=11, wrap=True)
            y -= 0.08
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        fig = _page("Evidence mapping")
        y = 0.82
        for item in result.evidence:
            text = item.description
            if item.channel_a_post_ids or item.channel_b_post_ids:
                text += f"\n@{a.username}: {', '.join(map(str, item.channel_a_post_ids)) or '—'}"
                text += f"\n@{b.username}: {', '.join(map(str, item.channel_b_post_ids)) or '—'}"
            fig.text(0.08, y, text, fontsize=11, va="top", wrap=True)
            y -= 0.16
        fig.text(0.08, 0.08, f"Методология: {result.methodology_version}", fontsize=9)
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)
    return path
