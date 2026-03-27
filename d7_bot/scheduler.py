from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from d7_bot.config import Config
from d7_bot.db import Database, moscow_today
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)

MOSCOW_TZ = "Europe/Moscow"


# ── Daily admin summary ────────────────────────────────────────────────────


async def daily_admin_summary(
    bot: Bot, db: Database, sheets: GoogleSheetsExporter, config: Config
) -> None:
    """
    Daily job: collect yesterday's tasks and send a summary to all admins.
    Also syncs data to Google Sheets if enabled.
    """
    yesterday = moscow_today() - timedelta(days=1)
    logger.info("Running daily_admin_summary for date: %s", yesterday)

    rows = await db.list_tasks_by_date(yesterday)
    if not rows:
        logger.info("No tasks reported for %s.", yesterday)
        report_text = (
            f"📊 <b>Отчёт за {html.escape(yesterday.isoformat())}</b>\n\nЗаданий не найдено."
        )
    else:
        lines: list[str] = [f"📊 <b>Отчёт за {html.escape(yesterday.isoformat())}</b>\n"]
        current_nick: str | None = None
        total = 0.0
        for d7_nick, wallet, task_code, cost_usdt, _payment_status in rows:
            if d7_nick != current_nick:
                current_nick = d7_nick
                lines.append(
                    f"\n👤 <b>{html.escape(str(d7_nick))}</b> "
                    f"(<code>{html.escape(str(wallet))}</code>)"
                )
            lines.append(
                f"  • <code>{html.escape(str(task_code))}</code> — {cost_usdt:.2f} USDT"
            )
            total += cost_usdt
        lines.append(f"\n💰 <b>Итого:</b> {total:.2f} USDT")
        report_text = "\n".join(lines)

    admin_ids = set(config.admin_ids) | set(await db.list_admins())
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, report_text)
        except Exception as exc:
            logger.warning("Could not send daily report to admin %s: %s", admin_id, exc)

    # Sync designers snapshot to Google Sheets.
    # Report rows are exported at report submission time; do not re-append them here.
    if sheets.is_enabled:
        designers = await db.list_designers()
        try:
            await sheets.sync_designers(designers)
        except Exception as exc:
            logger.error("Sheets sync_designers failed in scheduler: %s", exc)


# ── 08:00 MSK: morning reminder to all employees ──────────────────────────


async def morning_reminder_job(bot: Bot, db: Database) -> None:
    """
    Send a morning reminder to all registered employees at 08:00 MSK.
    Reminds them to submit yesterday's report by 12:00 MSK.
    """
    logger.info("Running morning_reminder_job")
    designers = await db.list_designers()
    if not designers:
        logger.info("No designers registered; skipping morning reminder.")
        return

    msg = (
        "🌅 <b>Доброе утро!</b>\n\n"
        "Напоминаю, что отчёт за вчера нужно сдать <b>сегодня до 12:00 МСК</b>.\n\n"
        "⚠️ Если отчёт не будет сдан до дедлайна, "
        "выплата переносится на следующий день."
    )

    sent = 0
    for designer in designers:
        try:
            await bot.send_message(designer.telegram_id, msg)
            sent += 1
        except Exception as exc:
            logger.warning(
                "Could not send morning reminder to %s (%s): %s",
                designer.d7_nick, designer.telegram_id, exc,
            )

    logger.info("Morning reminders sent to %d/%d employees.", sent, len(designers))


# ── 12:00 MSK: missed reports notification to admins ─────────────────────


async def missed_reports_job(bot: Bot, db: Database, config: Config) -> None:
    """
    At 12:00 MSK, notify admins about employees who haven't submitted yesterday's report.
    Does NOT send any message to the employees themselves.
    """
    yesterday = moscow_today() - timedelta(days=1)
    logger.info("Running missed_reports_job for date: %s", yesterday)

    from d7_bot.handlers.admin import _get_missed_text
    text = await _get_missed_text(db, yesterday)

    admin_ids = set(config.admin_ids) | set(await db.list_admins())
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning("Could not send missed reports to admin %s: %s", admin_id, exc)

    logger.info("Missed reports notification sent to %d admin(s).", len(admin_ids))


# ── Setup ──────────────────────────────────────────────────────────────────


def setup_scheduler(
    bot: Bot,
    db: Database,
    sheets: GoogleSheetsExporter,
    config: Config,
) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance with all scheduled jobs."""
    scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

    # Daily admin report — keep existing configurable hour (default 08:00 UTC via config)
    # We schedule it at config.report_hour_utc in UTC to preserve backward compat
    # but also run it in UTC timezone via the job
    scheduler.add_job(
        daily_admin_summary,
        trigger="cron",
        hour=config.report_hour_utc,
        minute=0,
        timezone="UTC",
        kwargs={"bot": bot, "db": db, "sheets": sheets, "config": config},
        id="daily_admin_summary",
        replace_existing=True,
    )
    logger.info("Daily admin summary scheduled at %02d:00 UTC.", config.report_hour_utc)

    # 08:00 MSK: morning reminder to all employees
    scheduler.add_job(
        morning_reminder_job,
        trigger="cron",
        hour=8,
        minute=0,
        timezone=MOSCOW_TZ,
        kwargs={"bot": bot, "db": db},
        id="morning_reminder",
        replace_existing=True,
    )
    logger.info("Morning reminder scheduled at 08:00 %s.", MOSCOW_TZ)

    # 12:00 MSK: missed reports notification to admins
    scheduler.add_job(
        missed_reports_job,
        trigger="cron",
        hour=12,
        minute=0,
        timezone=MOSCOW_TZ,
        kwargs={"bot": bot, "db": db, "config": config},
        id="missed_reports_noon",
        replace_existing=True,
    )
    logger.info("Missed reports job scheduled at 12:00 %s.", MOSCOW_TZ)

    return scheduler
