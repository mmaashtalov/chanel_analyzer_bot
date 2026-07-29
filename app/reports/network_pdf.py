from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.similarity.search import ProfileSearchResult


def build_network_pdf(result: ProfileSearchResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"network_{result.source_username}_v{result.source_version}.pdf"
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_axes((0.05, 0.08, 0.9, 0.84))
        ax.axis("off")
        ax.text(0.5, 0.95, f"Intelligence Network · @{result.source_username}", ha="center", va="top", fontsize=20, weight="bold")
        ax.text(0.5, 0.90, "Ближайшее окружение по сохранённым аналитическим профилям", ha="center", va="top", fontsize=11)
        ax.scatter([0], [0], s=1400)
        ax.text(0, 0, f"@{result.source_username}", ha="center", va="center", fontsize=10, weight="bold")
        count = max(1, len(result.candidates))
        for index, item in enumerate(result.candidates):
            angle = 2 * 3.141592653589793 * index / count
            radius = 1.4 + (index % 2) * 0.35
            x, y = radius * __import__("math").cos(angle), radius * __import__("math").sin(angle)
            ax.plot([0, x], [0, y], linewidth=max(0.7, item.overall_score * 3))
            ax.scatter([x], [y], s=650)
            ax.text(x, y, f"@{item.username}\n{item.overall_score:.0%}", ha="center", va="center", fontsize=8)
        ax.set_xlim(-2.4, 2.4)
        ax.set_ylim(-2.0, 2.0)
        ax.text(-2.3, -1.88, "Сходство не является доказательством общего автора, владельца или координации.", fontsize=8)
        pdf.savefig(fig)
        plt.close(fig)
    return path
