import asyncio

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.application.analyze_channel import AnalyzeChannelUseCase
from app.application.compare_channels import CompareChannelsUseCase
from app.application.find_similar_profiles import FindSimilarProfilesUseCase
from app.collection.base import ProviderError
from app.db.repositories import (
    EvolutionRepository,
    GraphRepository,
    JobRepository,
    MonitoringRepository,
)
from app.db.workspace_repository import WorkspaceRepository
from app.domain.models import ChannelRef
from app.evidence.contradictions import ContradictionResolutionAction
from app.evidence.review import ClaimReviewStatus
from app.reports.claim_timeline_pdf import build_claim_timeline_exports
from app.reports.contradiction_pdf import build_contradiction_exports
from app.reports.network_pdf import build_network_pdf
from app.reports.verification_pdf import build_verification_exports
from app.workspaces.models import WorkspaceItemType

logger = structlog.get_logger()


def _number(value: float | None) -> str:
    if value is None:
        return "н/д"
    if isinstance(value, float):
        return f"{value:,.1f}".replace(",", " ")
    return f"{value:,}".replace(",", " ")


def build_handlers(
    use_case: AnalyzeChannelUseCase,
    compare_use_case: CompareChannelsUseCase,
    similar_use_case: FindSimilarProfilesUseCase,
    repository: JobRepository,
    graph_repository: GraphRepository,
    evolution_repository: EvolutionRepository,
    monitoring_repository: MonitoringRepository,
    workspace_repository: WorkspaceRepository,
    workspace_report_use_case,
    workspace_changes_use_case,
    review_claims_use_case,
    acquire_evidence_use_case,
    corroborate_claims_use_case,
    track_claims_use_case,
    contradiction_use_case,
    report_output_dir,
):
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Telegram OSINT Analytics Platform\n\n"
                "/analyze @channel — PDF и evidence-first JSON\n"
                "/compare @channel1 @channel2 — сравнение профилей\n"
                "/similar @channel — ближайшие профили\n"
                "/network @channel — PDF-карта окружения\n"
                "/entity название — статистика сущности\n"
                "/domain example.com — статистика домена\n"
                "/timeline название — динамика упоминаний\n"
                "/changes @channel — изменения профиля\n"
                "/watch @channel [уровень] [часы] — мониторинг\n"
                "/unwatch @channel — снять с мониторинга\n"
                "/watches — список наблюдения\n"
                "/alerts — последние уведомления\n"
                "/digest — суточная сводка\n"
                "/workspace_create название — создать проект\n"
                "/workspaces — список проектов\n"
                "/workspace ID — открыть проект\n"
                "/workspace_add ID тип значение — добавить объект\n"
                "/workspace_remove ID тип значение — удалить объект\n"
                "/workspace_delete ID — удалить проект\n"
                "/workspace_report ID [дни] — сводный PDF Workspace\n"
                "/workspace_changes ID [дни] — изменения Workspace\n"
                "/claims ID [статус] — claims последнего provenance bundle\n"
                "/claim_review CLAIM_ID статус [комментарий] — верифицировать claim\n"
                "/claim_history CLAIM_ID — журнал решений\n"
                "/evidence_gaps ID — пробелы доказательной базы\n"
                "/verification_report ID — PDF и JSON review-отчёт\n"
                "/corroboration ID — независимость и corroboration claims\n"
                "/claim_timeline_build ID — построить timeline Workspace\n"
                "/claim_timeline CLAIM_ID — история утверждения\n"
                "/claim_timeline_report ID — PDF/JSON timeline\n"
                "/contradictions ID [open|all] — очередь противоречий\n"
                "/contradiction ID — карточка contradiction и журнал\n"
                "/contradiction_resolve ID confirm|compatible|newer|evidence [claim] [комментарий]\n"
                "/contradiction_report ID — PDF/JSON dossier\n"
                "/status — состояние последнего задания\n\n"
                "Система анализирует только каналы, явно указанные пользователем."
            )

    async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /analyze @channel")
            return
        try:
            channel = ChannelRef(context.args[0])
            status_message = await message.reply_text(f"0/5 Создаю задание для @{channel.username}…")

            async def progress(step: int, text: str) -> None:
                await status_message.edit_text(f"{step}/5 {text} · @{channel.username}")

            result = await use_case.execute(user.id, channel, progress)
            await status_message.edit_text(
                f"5/5 Анализ @{channel.username} завершён.\n"
                f"Постов: {_number(result.metrics.posts_count)}\n"
                f"Средний охват: {_number(result.metrics.mean_views)}\n"
                f"ER/1000: {_number(result.metrics.engagement_per_1000_views)}\n"
                f"Claims: {len(result.provenance.claims)} · Evidence: {len(result.provenance.evidence)}\n"
                f"Provenance completeness: {result.provenance.completeness:.0%}"
            )
            with result.report_path.open("rb") as report_file:
                await message.reply_document(document=report_file, filename=result.report_path.name, caption=f"Аналитический отчёт @{channel.username}")
            with result.provenance_path.open("rb") as provenance_file:
                await message.reply_document(
                    document=provenance_file,
                    filename=result.provenance_path.name,
                    caption=f"Evidence-first JSON-пакет @{channel.username}",
                )
        except (ProviderError, ValueError) as exc:
            await message.reply_text(str(exc))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("analyze_failed", user_id=user.id)
            await message.reply_text("Анализ завершился ошибкой. Детали записаны в журнал.")

    async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if len(context.args) < 2:
            await message.reply_text("Укажите два канала: /compare @channel1 @channel2")
            return
        try:
            channel_a, channel_b = ChannelRef(context.args[0]), ChannelRef(context.args[1])
            status_message = await message.reply_text(f"0/5 Готовлю сравнение @{channel_a.username} и @{channel_b.username}…")

            async def progress(step: int, text: str) -> None:
                await status_message.edit_text(f"{step}/5 {text}")

            result = await compare_use_case.execute(user.id, channel_a, channel_b, progress)
            score = result.similarity
            await status_message.edit_text(
                f"5/5 Сравнение завершено.\n"
                f"Общее сходство: {score.overall_score:.0%}\n"
                f"Стиль: {score.style_score:.0%} · Тематика: {score.narrative_score:.0%}\n"
                f"Время: {score.temporal_score:.0%} · Структура: {score.structural_score:.0%}\n"
                f"Confidence: {score.confidence:.0%}"
            )
            with result.report_path.open("rb") as report_file:
                await message.reply_document(document=report_file, filename=result.report_path.name, caption=f"Сравнение @{channel_a.username} ↔ @{channel_b.username}")
        except (ProviderError, ValueError) as exc:
            await message.reply_text(str(exc))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("compare_failed", user_id=user.id)
            await message.reply_text("Сравнение завершилось ошибкой. Детали записаны в журнал.")

    async def similar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /similar @channel [количество]")
            return
        try:
            limit = int(context.args[1]) if len(context.args) > 1 else 10
            result = await similar_use_case.execute(context.args[0], limit)
            if not result.candidates:
                await message.reply_text("В базе пока нет других профилей для сравнения.")
                return
            lines = [f"Ближайшие профили к @{result.source_username}:"]
            for index, item in enumerate(result.candidates, 1):
                lines.append(
                    f"{index}. @{item.username} — {item.overall_score:.0%} ({item.classification})\n"
                    f"   стиль {item.style_score:.0%} · тематика {item.narrative_score:.0%} · "
                    f"время {item.temporal_score:.0%} · структура {item.structural_score:.0%} · "
                    f"confidence {item.confidence:.0%}"
                )
            lines.append("\nСходство профилей не доказывает общего автора или координацию.")
            await message.reply_text("\n".join(lines))
        except (ValueError, LookupError) as exc:
            await message.reply_text(str(exc))
        except Exception:
            logger.exception("similar_failed")
            await message.reply_text("Поиск завершился ошибкой. Детали записаны в журнал.")

    async def network(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /network @channel")
            return
        try:
            result = await similar_use_case.execute(context.args[0], 10)
            if not result.candidates:
                await message.reply_text("В базе пока нет окружения для этого канала.")
                return
            path = build_network_pdf(result, report_output_dir)
            with path.open("rb") as report_file:
                await message.reply_document(
                    document=report_file,
                    filename=path.name,
                    caption=f"Intelligence Network @{result.source_username}",
                )
        except (ValueError, LookupError) as exc:
            await message.reply_text(str(exc))
        except Exception:
            logger.exception("network_failed")
            await message.reply_text("Построение сети завершилось ошибкой. Детали записаны в журнал.")

    async def entity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите сущность: /entity Ростех")
            return
        summary = await graph_repository.entity_summary(" ".join(context.args))
        if summary is None:
            await message.reply_text("Сущность пока не найдена в Intelligence Graph.")
            return
        lines = [
            f"{summary.display_name} · {summary.entity_type}",
            f"Упоминаний: {summary.total_mentions}",
            f"Публикаций: {summary.post_count}",
            f"Каналов: {summary.channel_count}",
            "",
            "Наиболее связанные каналы:",
        ]
        for item in summary.channels[:10]:
            lines.append(f"@{item.channel_username} — {item.mentions} упоминаний в {item.posts} постах")
        await message.reply_text("\n".join(lines))

    async def domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите домен: /domain example.com")
            return
        summary = await graph_repository.entity_summary(context.args[0], "domain")
        if summary is None:
            await message.reply_text("Домен пока не найден в Intelligence Graph.")
            return
        lines = [f"Домен {summary.display_name}", f"Ссылок/упоминаний: {summary.total_mentions}", f"Каналов: {summary.channel_count}", ""]
        lines.extend(f"@{item.channel_username} — {item.mentions}" for item in summary.channels[:15])
        await message.reply_text("\n".join(lines))

    async def timeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите сущность: /timeline Ростех")
            return
        buckets = await graph_repository.timeline(" ".join(context.args))
        if not buckets:
            await message.reply_text("Данных для временной шкалы пока нет.")
            return
        lines = [f"Динамика: {' '.join(context.args)}"]
        lines.extend(f"{item.period}: {item.mentions} упоминаний · {item.posts} постов" for item in buckets[-24:])
        await message.reply_text("\n".join(lines))

    async def changes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /changes @channel")
            return
        username = context.args[0].lower().lstrip("@")
        records = await evolution_repository.latest_changes(username, 20)
        if not records:
            await message.reply_text("Для канала пока нет сравнимых версий. Выполните /analyze повторно после появления новых публикаций.")
            return
        latest_version = max(item.to_version for item in records)
        latest = [item for item in records if item.to_version == latest_version]
        icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
        lines = [f"Изменения @{username}: v{latest[0].from_version} → v{latest_version}"]
        for item in latest[:10]:
            delta = f" · {item.delta:+.0%}" if item.delta is not None and item.event_type == "metric_shift" else ""
            lines.append(
                f"{icons.get(item.severity, '•')} {item.title}{delta}\n"
                f"   confidence {item.confidence:.0%}"
            )
        await message.reply_text("\n".join(lines))

    async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /history @channel")
            return
        username = context.args[0].lower().lstrip("@")
        versions = await evolution_repository.history(username)
        if not versions:
            await message.reply_text("Профиль канала пока не найден.")
            return
        lines = [f"История @{username}: {len(versions)} версий"]
        for item in versions[:20]:
            lines.append(
                f"v{item.version} · {item.collected_at:%Y-%m-%d %H:%M UTC} · "
                f"{item.source_post_count} постов · confidence {item.confidence:.0%}"
            )
        await message.reply_text("\n".join(lines))


    async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user, chat = update.effective_message, update.effective_user, update.effective_chat
        if message is None or user is None or chat is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /watch @channel [high|medium|low|critical] [интервал_часов]")
            return
        try:
            channel = ChannelRef(context.args[0])
            sensitivity = context.args[1].casefold() if len(context.args) > 1 else "high"
            hours = int(context.args[2]) if len(context.args) > 2 else 6
            record = await monitoring_repository.add_watch(
                user.id, chat.id, channel.username, sensitivity, hours * 60
            )
            await message.reply_text(
                f"@{record.channel_username} добавлен под наблюдение.\n"
                f"Проверка: каждые {record.interval_minutes // 60} ч.\n"
                f"Уведомления: {record.sensitivity} и выше."
            )
        except (ValueError, TypeError) as exc:
            await message.reply_text(str(exc))

    async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Укажите канал: /unwatch @channel")
            return
        channel = ChannelRef(context.args[0])
        removed = await monitoring_repository.remove_watch(user.id, channel.username)
        await message.reply_text(
            f"@{channel.username} снят с наблюдения." if removed else "Такого канала в вашем списке нет."
        )

    async def watches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        records = await monitoring_repository.list_watches(user.id)
        if not records:
            await message.reply_text("Ваш список наблюдения пуст.")
            return
        lines = [f"Под наблюдением: {len(records)}"]
        for item in records[:50]:
            state = "включено" if item.enabled else "приостановлено"
            lines.append(
                f"@{item.channel_username} · {item.sensitivity} · {item.interval_minutes // 60} ч · {state}"
            )
        await message.reply_text("\n".join(lines))

    async def alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        records = await monitoring_repository.recent_alerts(user.id, 24 * 7, 30)
        if not records:
            await message.reply_text("За последние 7 дней уведомлений нет.")
            return
        icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
        lines = ["Последние уведомления:"]
        for item in records:
            lines.append(
                f"{icons.get(item.severity, '•')} @{item.channel_username} · {item.title} · confidence {item.confidence:.0%}"
            )
        await message.reply_text("\n".join(lines))

    async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        watched, counts = await monitoring_repository.digest(user.id, 24)
        records = await monitoring_repository.recent_alerts(user.id, 24, 5)
        lines = [
            "Сводка за 24 часа",
            f"Под наблюдением: {watched}",
            f"Critical: {counts.get('critical', 0)}",
            f"High: {counts.get('high', 0)}",
            f"Medium: {counts.get('medium', 0)}",
            f"Low: {counts.get('low', 0)}",
        ]
        if records:
            lines.append("\nГлавные изменения:")
            lines.extend(f"• @{item.channel_username}: {item.title}" for item in records)
        await message.reply_text("\n".join(lines))


    async def workspace_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        if not context.args:
            await message.reply_text("Укажите название: /workspace_create ОПК")
            return
        try:
            item = await workspace_repository.create(user.id, " ".join(context.args))
            await message.reply_text(f"Workspace создан: {item.name}\nID: {item.id}")
        except ValueError as exc:
            await message.reply_text(str(exc))

    async def workspaces(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        records = await workspace_repository.list(user.id)
        if not records:
            await message.reply_text("У вас пока нет Workspaces.")
            return
        lines = [f"Workspaces: {len(records)}"]
        for item in records:
            lines.append(f"{item.name} · {item.id[:8]} · объектов {len(item.items)}")
        await message.reply_text("\n".join(lines))

    async def workspace_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        if not context.args:
            await message.reply_text("Укажите ID: /workspace ID")
            return
        item = await workspace_repository.get(user.id, context.args[0])
        if item is None:
            await message.reply_text("Workspace не найден.")
            return
        counts = item.counts()
        lines = [item.name, f"ID: {item.id}", f"Объектов: {len(item.items)}", "",
                 " · ".join(f"{k}: {v}" for k, v in counts.items() if v)]
        lines.extend(f"{obj.item_type.value}: {obj.value}" for obj in item.items[:50])
        await message.reply_text("\n".join(lines))

    async def workspace_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        if len(context.args) < 3:
            await message.reply_text("Формат: /workspace_add ID channel|rss|domain|entity|keyword значение")
            return
        try:
            kind = WorkspaceItemType.parse(context.args[1])
            item = await workspace_repository.add_item(user.id, context.args[0], kind, " ".join(context.args[2:]))
            await message.reply_text(f"Добавлено в {item.name}. Объектов: {len(item.items)}")
        except (ValueError, LookupError) as exc:
            await message.reply_text(str(exc))

    async def workspace_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        if len(context.args) < 3:
            await message.reply_text("Формат: /workspace_remove ID тип значение")
            return
        try:
            removed = await workspace_repository.remove_item(user.id, context.args[0], WorkspaceItemType.parse(context.args[1]), " ".join(context.args[2:]))
            await message.reply_text("Объект удалён." if removed else "Объект не найден.")
        except ValueError as exc:
            await message.reply_text(str(exc))

    async def workspace_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None: return
        if not context.args:
            await message.reply_text("Укажите ID: /workspace_delete ID")
            return
        removed = await workspace_repository.delete(user.id, context.args[0])
        await message.reply_text("Workspace удалён." if removed else "Workspace не найден.")

    async def workspace_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Укажите ID: /workspace_report ID [дни]")
            return
        try:
            lookback_days = int(context.args[1]) if len(context.args) > 1 else 30
            if not 1 <= lookback_days <= 3650:
                raise ValueError("Период должен быть от 1 до 3650 дней")
            status_message = await message.reply_text("Собираю Workspace Intelligence Report…")
            report, path = await workspace_report_use_case.execute(user.id, context.args[0], lookback_days)
            await status_message.edit_text(
                f"Workspace Report готов.\n"
                f"Покрытие: {report.coverage_ratio:.0%}\n"
                f"Каналов: {report.analyzed_channel_count}/{report.requested_channel_count}\n"
                f"Публикаций: {_number(report.total_posts)}\n"
                f"Confidence: {report.weighted_confidence:.0%}"
            )
            with path.open("rb") as report_file:
                await message.reply_document(
                    document=report_file, filename=path.name,
                    caption=f"Workspace Intelligence · {report.workspace_name}",
                )
        except (ValueError, LookupError) as exc:
            await message.reply_text(str(exc))
        except Exception:
            logger.exception("workspace_report_failed", user_id=user.id)
            await message.reply_text("Не удалось сформировать Workspace Report. Детали записаны в журнал.")


    async def workspace_changes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Укажите ID: /workspace_changes ID [дни]")
            return
        try:
            lookback_days = int(context.args[1]) if len(context.args) > 1 else 30
            lookback_days = max(1, min(365, lookback_days))
            report, path = await workspace_changes_use_case.execute(user.id, context.args[0], lookback_days)
            await message.reply_text(
                f"Workspace trend: {report.trend.value}\n"
                f"Confidence: {report.confidence:.0%}\n"
                f"Наблюдений: {len(report.observations)}"
            )
            with path.open("rb") as report_file:
                await message.reply_document(report_file, filename=path.name)
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))
        except Exception:
            logger.exception("workspace_changes_failed", user_id=user.id)
            await message.reply_text("Не удалось сформировать отчёт изменений Workspace")

    async def claims(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /claims WORKSPACE_ID [unreviewed|verified|partially_verified|rejected|needs_more_evidence]")
            return
        try:
            status_filter = ClaimReviewStatus.parse(context.args[1]) if len(context.args) > 1 else None
            bundle, records = await review_claims_use_case.list_claims(user.id, context.args[0], status_filter)
            lines = [
                f"Claims: {len(records)} · review completeness {bundle.get('review_completeness', 0):.0%}",
                f"Integrity: {bundle.get('integrity_hash', 'н/д')[:16]}…",
            ]
            for claim in records[:10]:
                lines.append(
                    f"\n{claim['claim_index']}. {claim['statement']}\n"
                    f"ID: {claim['claim_id']}\n"
                    f"Статус: {claim.get('review_status', 'unreviewed')} · "
                    f"Confidence {claim.get('confidence', 0):.0%} · Evidence {claim.get('evidence_quality', 0):.0%}"
                )
            if len(records) > 10:
                lines.append(f"\nПоказаны первые 10 из {len(records)}.")
            await message.reply_text("\n".join(lines))
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def claim_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if len(context.args) < 2:
            await message.reply_text(
                "Формат: /claim_review CLAIM_ID verified|partial|rejected|needs_evidence [комментарий]"
            )
            return
        try:
            review_status = ClaimReviewStatus.parse(context.args[1])
            comment = " ".join(context.args[2:]).strip() or None
            bundle = await review_claims_use_case.review(
                user.id, context.args[0], review_status, comment
            )
            reviewed = next(
                item for item in bundle["claims"] if item["claim_id"] == context.args[0]
            )
            await message.reply_text(
                f"Claim обновлён: {reviewed['review_status']}\n"
                f"Confidence: {reviewed['confidence']:.0%}\n"
                f"Evidence quality: {reviewed['evidence_quality']:.0%}\n"
                f"Review completeness: {bundle['review_completeness']:.0%}\n"
                f"Новый integrity hash: {bundle['integrity_hash']}"
            )
        except (LookupError, PermissionError, ValueError, StopIteration) as exc:
            await message.reply_text(str(exc))

    async def claim_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /claim_history CLAIM_ID")
            return
        try:
            records = await review_claims_use_case.history(user.id, context.args[0])
            if not records:
                await message.reply_text("Для claim ещё нет решений аналитика.")
                return
            lines = ["История claim:"]
            for item in records[-10:]:
                lines.append(
                    f"{item['created_at']} · {item['previous_status']} → {item['new_status']}"
                    + (f" · {item['comment']}" if item['comment'] else "")
                    + f"\nHash: {item['event_hash'][:16]}…"
                )
            await message.reply_text("\n".join(lines))
        except (LookupError, PermissionError) as exc:
            await message.reply_text(str(exc))

    async def evidence_gaps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /evidence_gaps WORKSPACE_ID")
            return
        try:
            bundle, gaps = await review_claims_use_case.gaps(user.id, context.args[0])
            if not gaps:
                await message.reply_text("Критичных пробелов доказательной базы не выявлено.")
                return
            lines = [
                f"Evidence gaps: {len(gaps)} · bundle completeness {bundle.get('completeness', 0):.0%}"
            ]
            for gap in gaps[:20]:
                lines.append(
                    f"\n[{gap.severity.upper()}] {gap.code}\nClaim: {gap.claim_id}\n{gap.description}"
                )
            await message.reply_text("\n".join(lines))
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def verification_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /verification_report WORKSPACE_ID")
            return
        try:
            bundle, _ = await review_claims_use_case.list_claims(user.id, context.args[0])
            json_path, pdf_path = build_verification_exports(bundle, report_output_dir)
            with pdf_path.open("rb") as pdf_file:
                await message.reply_document(
                    document=pdf_file,
                    filename=pdf_path.name,
                    caption="Analyst Verification Report",
                )
            with json_path.open("rb") as json_file:
                await message.reply_document(
                    document=json_file,
                    filename=json_path.name,
                    caption="Machine-readable verification bundle",
                )
        except LookupError as exc:
            await message.reply_text(str(exc))
        except Exception:
            logger.exception("verification_report_failed", user_id=user.id)
            await message.reply_text("Не удалось сформировать verification report")


    async def corroboration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /corroboration WORKSPACE_ID")
            return
        try:
            report = await corroborate_claims_use_case.assess(user.id, context.args[0])
            lines = [
                f"Source Independence · {report['methodology_version']}",
                f"Integrity: {report['integrity_hash'][:16]}…",
            ]
            for item in report["claims"][:10]:
                lines.append(
                    f"\n{item['statement']}\n"
                    f"Independence: {item['independence_score']:.0%} · "
                    f"Corroboration: {item['corroboration_score']:.0%}\n"
                    f"Документы: {item['document_count']} · независимые кластеры: "
                    f"{item['independent_cluster_count']}"
                    + (f"\nОграничения: {'; '.join(item['caveats'])}" if item['caveats'] else "")
                )
            await message.reply_text("\n".join(lines))
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def claim_timeline_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /claim_timeline_build WORKSPACE_ID")
            return
        try:
            report = await track_claims_use_case.build(user.id, context.args[0])
            await message.reply_text(
                f"Temporal claims построены\nIdentities: {report['identity_count']} · "
                f"claims: {report['claim_count']} · relations: {report['relation_count']}\n"
                f"Integrity: {report['integrity_hash'][:16]}…"
            )
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def claim_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /claim_timeline CLAIM_ID")
            return
        try:
            report = await track_claims_use_case.timeline(user.id, context.args[0])
            lines = [f"Claim identity: {report['claim_identity_id']}", report['canonical_statement']]
            for item in report['claims']:
                lines.append(
                    f"\n{item['generated_at']} · {item['temporal_status']}\n"
                    f"{item['claim_id']}\n{item['statement']}"
                )
            if report['relations']:
                lines.append("\nRelations:")
                for relation in report['relations']:
                    lines.append(
                        f"{relation['source_claim_id']} → {relation['target_claim_id']}: "
                        f"{relation['relation_type']} ({relation['confidence']:.0%})"
                    )
            await message.reply_text("\n".join(lines))
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def claim_timeline_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /claim_timeline_report WORKSPACE_ID")
            return
        try:
            report = await track_claims_use_case.build(user.id, context.args[0])
            json_path, pdf_path = build_claim_timeline_exports(report, report_output_dir)
            with pdf_path.open("rb") as file:
                await message.reply_document(file, filename=pdf_path.name, caption="Temporal Claim Timeline")
            with json_path.open("rb") as file:
                await message.reply_document(file, filename=json_path.name, caption="Machine-readable timeline")
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def contradictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /contradictions WORKSPACE_ID [open|confirmed|compatible|all]")
            return
        status_filter = context.args[1] if len(context.args) > 1 else "open"
        try:
            records = await contradiction_use_case.queue(user.id, context.args[0], status_filter)
            if not records:
                await message.reply_text("В выбранной очереди противоречий нет.")
                return
            lines = [f"Contradictions: {len(records)} · filter {status_filter}"]
            for item in records:
                lines.append(
                    f"\n{item['contradiction_id']} · {item['severity']} · "
                    f"confidence {item['confidence']:.0%} · {item['status']}"
                    f"\nS: {str(item['source_statement'] or '')[:220]}"
                    f"\nT: {str(item['target_statement'] or '')[:220]}"
                )
            await message.reply_text("\n".join(lines))
        except (LookupError, PermissionError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def contradiction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /contradiction CONTRADICTION_ID")
            return
        try:
            item = await contradiction_use_case.detail(user.id, context.args[0])
            lines = [
                f"Contradiction {item['contradiction_id']}",
                (
                    f"Статус: {item['status']} · severity {item['severity']} · "
                    f"confidence {item['confidence']:.0%}"
                ),
                f"Source: {item['source_claim_id']}\n{item['source_statement']}",
                f"Target: {item['target_claim_id']}\n{item['target_statement']}",
                f"Rationale: {'; '.join(item.get('rationale') or [])}",
                f"Решение: {item.get('resolution_action') or 'не принято'}",
            ]
            if item.get("history"):
                lines.append("\nЖурнал:")
                for event in item["history"][-10:]:
                    lines.append(
                        f"{event['created_at']} · {event['action']} · "
                        f"{event['previous_status'] or 'new'} → {event['new_status']}"
                        f"\nHash: {event['event_hash'][:16]}…"
                    )
            await message.reply_text("\n".join(lines))
        except (LookupError, PermissionError) as exc:
            await message.reply_text(str(exc))

    async def contradiction_resolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if len(context.args) < 2:
            await message.reply_text(
                "Формат: /contradiction_resolve ID confirm|compatible|newer|evidence [CLAIM_ID] [комментарий]"
            )
            return
        try:
            action = ContradictionResolutionAction.parse(context.args[1])
            selected_claim_id = None
            comment_start = 2
            if action is ContradictionResolutionAction.ACCEPT_NEWER:
                if len(context.args) < 3:
                    await message.reply_text("Для action newer укажите CLAIM_ID нового утверждения.")
                    return
                selected_claim_id = context.args[2]
                comment_start = 3
            comment = " ".join(context.args[comment_start:]).strip() or None
            result = await contradiction_use_case.resolve(
                user.id,
                context.args[0],
                action,
                selected_claim_id,
                comment,
            )
            response = (
                f"Contradiction обновлён: {result['status']}\n"
                f"Action: {result['resolution_action']}\n"
                f"Event hash: {result.get('last_event_hash', '')}"
            )
            if result.get("evidence_request_id"):
                response += f"\nEvidence request: {result['evidence_request_id']}"
            await message.reply_text(response)
        except (LookupError, PermissionError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def contradiction_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /contradiction_report WORKSPACE_ID [all|open]")
            return
        try:
            status_filter = context.args[1] if len(context.args) > 1 else "all"
            report = await contradiction_use_case.report(user.id, context.args[0], status_filter)
            json_path, pdf_path = build_contradiction_exports(report, report_output_dir)
            with pdf_path.open("rb") as file:
                await message.reply_document(file, filename=pdf_path.name, caption="Contradiction Dossier")
            with json_path.open("rb") as file:
                await message.reply_document(file, filename=json_path.name, caption="Machine-readable contradiction dossier")
        except (LookupError, PermissionError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def evidence_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if len(context.args) < 2:
            await message.reply_text("Формат: /evidence_request WORKSPACE_ID CLAIM_ID")
            return
        try:
            record = await acquire_evidence_use_case.create_for_claim(user.id, context.args[0], context.args[1])
            await message.reply_text(
                f"Evidence request создан: {record['id']}\n"
                f"Статус: {record['status']} · priority {record['priority']}\n"
                f"Пробелы: {', '.join(record['gap_codes']) or 'нет'}\n"
                f"Источников в плане: {len(record['source_plan'])}"
            )
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def evidence_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        try:
            workspace_id = context.args[0] if context.args else None
            records = await acquire_evidence_use_case.list_requests(user.id, workspace_id)
            if not records:
                await message.reply_text("Evidence requests отсутствуют.")
                return
            lines = [f"Evidence requests: {len(records)}"]
            for item in records[:20]:
                lines.append(
                    f"\n{item['id']} · {item['status']} · {item['priority']}\n"
                    f"Claim: {item['claim_id']}\n"
                    f"Попытки: {item['attempts']}/{item['max_attempts']} · "
                    f"documents {item['documents_collected']}/{item['documents_linked']}"
                    + (f"\nСледующая попытка: {item['next_attempt_at']}" if item.get('next_attempt_at') else "")
                )
            await message.reply_text("\n".join(lines))
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def evidence_request_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /evidence_request_cancel REQUEST_ID")
            return
        try:
            record = await acquire_evidence_use_case.cancel(user.id, context.args[0])
            await message.reply_text(f"Request {record['id']} отменён.")
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def evidence_request_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /evidence_request_retry REQUEST_ID")
            return
        try:
            record = await acquire_evidence_use_case.retry(user.id, context.args[0])
            await message.reply_text(f"Request {record['id']} возвращён в очередь.")
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def evidence_request_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /evidence_request_run REQUEST_ID")
            return
        try:
            record = await acquire_evidence_use_case.run(user.id, context.args[0])
            await message.reply_text(
                f"Request {record['id']}: {record['status']}\n"
                f"Найдено документов: {record['documents_collected']}\n"
                f"Новых связей: {record['documents_linked']}"
                + (f"\nПричина: {record['last_error']}" if record['last_error'] else "")
            )
        except (LookupError, ValueError) as exc:
            await message.reply_text(str(exc))

    async def evidence_request_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        if not context.args:
            await message.reply_text("Формат: /evidence_request_history REQUEST_ID")
            return
        try:
            records = await acquire_evidence_use_case.history(user.id, context.args[0])
            lines = ["История evidence request:"]
            for item in records[-15:]:
                lines.append(
                    f"{item['created_at']} · {item['previous_status'] or 'new'} → {item['new_status']}"
                    f"\nHash: {item['event_hash'][:16]}…"
                )
            await message.reply_text("\n".join(lines))
        except LookupError as exc:
            await message.reply_text(str(exc))

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        record = await repository.latest_for_user(user.id)
        if record is None:
            await message.reply_text("У вас ещё нет заданий.")
            return
        text = (
            f"Задание {record.id[:8]}\nКанал(ы): {record.channel_username}\n"
            f"Статус: {record.status}\nЭтап: {record.progress_step}/5 — {record.progress_text or 'н/д'}"
        )
        if record.error_message:
            text += f"\nОшибка: {record.error_message[:500]}"
        await message.reply_text(text)

    return (
        start, analyze, compare, similar, network, entity, domain, timeline,
        changes, history, watch, unwatch, watches, alerts, digest, workspace_create,
        workspaces, workspace_show, workspace_add, workspace_remove, workspace_delete, workspace_report, workspace_changes, claims, claim_review, claim_history, evidence_gaps, verification_report, corroboration, claim_timeline_build, claim_timeline, claim_timeline_report, evidence_request, evidence_requests, evidence_request_cancel, evidence_request_retry, evidence_request_run, evidence_request_history, status,
        contradictions, contradiction, contradiction_resolve, contradiction_report,
    )
