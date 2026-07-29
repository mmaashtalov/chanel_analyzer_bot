from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from app.analytics.metrics import QuantitativeMetrics
from app.analytics.advanced import AdvancedAnalytics, calculate_advanced
from app.domain.models import ChannelSnapshot
from app.profiling.models import ContentDNAProfile


def _fmt(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "н/д"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return f"{value:,.{digits}f}".replace(",", " ")


def _new_page(title: str):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=20, fontweight="bold", x=0.06, ha="left")
    return fig


def build_quantitative_pdf(
    snapshot: ChannelSnapshot,
    metrics: QuantitativeMetrics,
    output_dir: Path,
    job_id: str,
    advanced: AdvancedAnalytics | None = None,
    content_dna: ContentDNAProfile | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{snapshot.username}_{job_id}.pdf"
    posts = sorted(snapshot.posts, key=lambda post: post.published_at)
    advanced = advanced or calculate_advanced(snapshot)

    with PdfPages(path) as pdf:
        fig = _new_page(f"Аналитический отчёт @{snapshot.username}")
        lines = [
            snapshot.title,
            f"Собрано постов: {_fmt(metrics.posts_count)}",
            f"Подписчиков: {_fmt(snapshot.subscribers)}",
            f"Средний охват: {_fmt(metrics.mean_views)}",
            f"Медианный охват: {_fmt(metrics.median_views)}",
            f"Средние реакции: {_fmt(metrics.mean_reactions)}",
            f"ER на 1 000 просмотров: {_fmt(metrics.engagement_per_1000_views, 2)}",
            f"Средняя длина поста: {_fmt(metrics.mean_post_length)} символов",
            f"Постов в день: {_fmt(metrics.posts_per_day, 2)}",
            f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ]
        fig.text(0.07, 0.80, "\n\n".join(lines), fontsize=14, va="top")
        fig.text(
            0.07,
            0.08,
            "Ограничение: отчёт отражает доступные публичные данные и не доказывает "
            "авторство или принадлежность к сетке.",
            fontsize=9,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig = _new_page("Executive Summary")
        y = 0.80
        for item in advanced.executive_summary:
            fig.text(0.08, y, "• " + item, fontsize=14, va="top", wrap=True)
            y -= 0.10
        fig.text(0.08, 0.10, "Выводы рассчитаны по доступной выборке и требуют аналитической интерпретации.", fontsize=9)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        if posts:
            fig = _new_page("Динамика просмотров")
            ax = fig.add_axes([0.08, 0.12, 0.86, 0.72])
            dated = [(p.published_at, p.views) for p in posts if p.views is not None]
            if dated:
                ax.plot([item[0] for item in dated], [item[1] for item in dated], linewidth=1)
                ax.axhline(metrics.mean_views or 0, linestyle="--", label="Среднее")
                ax.legend()
            ax.set_xlabel("Дата")
            ax.set_ylabel("Просмотры")
            ax.grid(alpha=0.25)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Матрица публикационной активности")
            ax = fig.add_axes([0.10, 0.14, 0.78, 0.68])
            matrix = np.zeros((7, 24), dtype=int)
            for post in posts:
                matrix[post.published_at.weekday(), post.published_at.hour] += 1
            image = ax.imshow(matrix, aspect="auto")
            ax.set_yticks(range(7), ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"])
            ax.set_xticks(range(0, 24, 2))
            ax.set_xlabel("Час публикации (UTC)")
            fig.colorbar(image, ax=ax, label="Количество постов")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Длина поста и охват")
            ax = fig.add_axes([0.10, 0.14, 0.82, 0.68])
            points = [
                (len(p.text), p.views, p.reactions or 0)
                for p in posts
                if p.views is not None
            ]
            if points:
                sizes = [max(12, min(250, reaction + 12)) for _, _, reaction in points]
                ax.scatter(
                    [x for x, _, _ in points],
                    [y for _, y, _ in points],
                    s=sizes,
                    alpha=0.45,
                )
            ax.set_xlabel("Длина поста, символы")
            ax.set_ylabel("Просмотры")
            ax.grid(alpha=0.25)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Эффективность по времени")
            ax = fig.add_axes([0.10, 0.14, 0.82, 0.68])
            hourly: dict[int, list[int]] = defaultdict(list)
            for post in posts:
                if post.views is not None:
                    hourly[post.published_at.hour].append(post.views)
            hours = list(range(24))
            values = [sum(hourly[h]) / len(hourly[h]) if hourly[h] else 0 for h in hours]
            ax.bar(hours, values)
            ax.set_xlabel("Час публикации (UTC)")
            ax.set_ylabel("Средний охват")
            ax.set_xticks(range(0, 24, 2))
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Частота постинга и средний охват")
            ax = fig.add_axes([0.10, 0.14, 0.82, 0.68])
            daily: dict[str, list] = defaultdict(list)
            for post in posts:
                daily[post.published_at.date().isoformat()].append(post)
            grouped: dict[int, list[int]] = defaultdict(list)
            for daily_posts in daily.values():
                day_views = [p.views for p in daily_posts if p.views is not None]
                if day_views:
                    grouped[len(daily_posts)].append(int(sum(day_views) / len(day_views)))
            frequencies = sorted(grouped)
            ax.plot(
                frequencies,
                [sum(grouped[f]) / len(grouped[f]) for f in frequencies],
                marker="o",
            )
            ax.set_xlabel("Постов в день")
            ax.set_ylabel("Средний охват")
            ax.grid(alpha=0.25)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Структура контента")
            ax = fig.add_axes([0.12, 0.15, 0.76, 0.66])
            lengths = [len(p.text) for p in posts]
            counts = [
                sum(v < 300 for v in lengths),
                sum(300 <= v < 1000 for v in lengths),
                sum(v >= 1000 for v in lengths),
            ]
            ax.pie(
                counts,
                labels=["Короткие <300", "Средние 300–999", "Лонгриды ≥1000"],
                autopct="%1.1f%%",
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Топ постов по вовлечённости")
            ranked = sorted(
                posts,
                key=lambda p: ((p.reactions or 0) / p.views if p.views else 0),
                reverse=True,
            )[:10]
            y = 0.82
            for index, post in enumerate(ranked, start=1):
                excerpt = post.text.replace("\n", " ")[:140]
                line = (
                    f"{index}. {post.published_at:%d.%m.%Y} · {_fmt(post.views)} просмотров · "
                    f"{_fmt(post.reactions)} реакций\n{excerpt}\n{post.url or ''}"
                )
                fig.text(0.07, y, line, fontsize=9, va="top")
                y -= 0.075
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Семантическое ядро")
            ax = fig.add_axes([0.18, 0.14, 0.72, 0.68])
            terms = list(advanced.top_terms[:15])
            if terms:
                labels = [t for t, _ in terms][::-1]
                values = [v for _, v in terms][::-1]
                ax.barh(labels, values)
                ax.set_xlabel("Частота")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Корреляции и устойчивость")
            rows = [
                ("Длина ↔ охват", advanced.length_views_correlation),
                ("Длина ↔ вовлечение", advanced.length_engagement_correlation),
                ("Ссылки ↔ вовлечение", advanced.links_engagement_correlation),
                ("Регулярность публикаций", advanced.publishing_stability),
            ]
            y = 0.78
            for label, value in rows:
                fig.text(0.10, y, f"{label}: {_fmt(value, 3)}", fontsize=15)
                y -= 0.12
            fig.text(0.10, y, f"Максимальная пауза: {_fmt(advanced.longest_silence_hours, 1)} ч", fontsize=15)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Аномалии")
            y = 0.82
            if not advanced.anomalies:
                fig.text(0.08, y, "Статистически значимые аномалии не обнаружены.", fontsize=14)
            for anomaly in advanced.anomalies[:10]:
                fig.text(0.08, y, f"Пост {anomaly.message_id} · {anomaly.kind} · score {anomaly.score}\n{anomaly.reason}\n{anomaly.url or ''}", fontsize=10, va="top")
                y -= 0.085
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        if content_dna is not None:
            fig = _new_page("Content DNA — цифровой профиль")
            fig.text(
                0.07,
                0.84,
                f"Выборка: {content_dna.sample_size} из {content_dna.source_post_count} постов · "
                f"уверенность: {content_dna.confidence:.0%}",
                fontsize=12,
            )
            ax = fig.add_axes([0.12, 0.18, 0.76, 0.56])
            labels = [trait.name for trait in content_dna.traits][::-1]
            scores = [trait.score for trait in content_dna.traits][::-1]
            ax.barh(labels, scores)
            ax.set_xlim(0, 1)
            ax.set_xlabel("Нормированный показатель")
            ax.grid(axis="x", alpha=0.25)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Content DNA — измеримые признаки")
            rows = [
                ("Лексическое разнообразие", content_dna.lexical_diversity),
                ("Средняя длина предложения", content_dna.mean_sentence_length),
                ("Среднее число абзацев", content_dna.mean_paragraphs),
                ("Эмодзи на пост", content_dna.emoji_rate),
                ("Вопросы на пост", content_dna.question_rate),
                ("Восклицания на пост", content_dna.exclamation_rate),
                ("Многоточия на пост", content_dna.ellipsis_rate),
                ("Длинные тире на пост", content_dna.dash_rate),
                ("Доля постов со ссылками", content_dna.link_rate),
                ("Доля прямых обращений", content_dna.direct_address_rate),
            ]
            y = 0.82
            for label, value in rows:
                fig.text(0.08, y, f"{label}: {_fmt(value, 3)}", fontsize=12)
                y -= 0.06
            markers = ", ".join(content_dna.dominant_markers) or "не выявлены"
            fig.text(0.08, 0.16, "Доминирующие маркеры: " + markers, fontsize=11, wrap=True)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Content DNA — доказательства")
            y = 0.84
            for trait in content_dna.traits:
                fig.text(
                    0.07, y,
                    f"{trait.name}: {trait.score:.0%} · confidence {trait.confidence:.0%}\n{trait.explanation}",
                    fontsize=10, va="top", wrap=True,
                )
                y -= 0.075
                for evidence in trait.evidence[:2]:
                    fig.text(
                        0.10, y,
                        f"Пост {evidence.message_id}: {evidence.excerpt}\n{evidence.url or ''}",
                        fontsize=8, va="top", wrap=True,
                    )
                    y -= 0.07
                    if y < 0.10:
                        break
                if y < 0.10:
                    break
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            fig = _new_page("Content DNA — повторяющиеся фразы и ограничения")
            y = 0.82
            if content_dna.repeated_phrases:
                for phrase, count in content_dna.repeated_phrases[:10]:
                    fig.text(0.08, y, f"{phrase} — {count}", fontsize=11)
                    y -= 0.055
            else:
                fig.text(0.08, y, "Устойчивые повторяющиеся фразы не выявлены.", fontsize=11)
                y -= 0.10
            fig.text(0.08, y - 0.02, "Ограничения методологии", fontsize=13, fontweight="bold")
            y -= 0.09
            for item in content_dna.limitations:
                fig.text(0.08, y, "• " + item, fontsize=10, wrap=True)
                y -= 0.065
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    return path
