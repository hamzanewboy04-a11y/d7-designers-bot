from __future__ import annotations

import logging
from datetime import date, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from d7_bot.config import Config
from d7_bot.db import Database
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)


async def scheduler_job(bot: Bot, db: Database, sheets: GoogleSheetsExporter, config: Config) -> None:
    """
    Daily job: collect yesterday's tasks and send a summary to all admins.
    Also syncs data to Google Sheets if enabled.
    """
    yesterday = date.today() - timedelta(days=1)
    logger.info("Running scheduler_job for date: %s", yesterday)

    rows = await db.list_tasks_by_date(yesterday)
    if not rows:
        logger.info("No tasks reported for %s.", yesterday)
        report_text = f"📊 <b>Отчёт за {yesterday.isoformat()}</b>\n\nЗаданий не найдено."
    else:
        import html as _html
        lines: list[str] = [f"📊 <b>Отчёт за {yesterday.isoformat()}</b>\n"]
        current_nick: str | None = None
        total = 0.0
        for d7_nick, wallet, task_code, cost_usdt, _payment_status in rows:
            if d7_nick != current_nick:
                current_nick = d7_nick
                lines.append(
                    f"\n👤 <b>{_html.escape(str(d7_nick))}</b> "
                    f"(<code>{_html.escape(str(wallet))}</code>)"
                )
            lines.append(f"  • <code>{_html.escape(str(task_code))}</code> — {cost_usdt:.2f} USDT")
            total += cost_usdt
        lines.append(f"\n💰 <b>Итого:</b> {total:.2f} USDT")
        report_text = "\n".join(lines)

    # Send to config admins + DB admins
    admin_ids = set(config.admin_ids) | set(await db.list_admins())
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, report_text)
        except Exception as exc:
            logger.warning("Could not send daily report to admin %s: %s", admin_id, exc)

    # Sync to Google Sheets
    if sheets.is_enabled:
        designers = await db.list_designers()
        try:
            await sheets.sync_designers(designers)
        except Exception as exc:
            logger.error("Sheets sync_designers failed in scheduler: %s", exc)

        if rows:
            # Group rows by designer for sheets exporter
            from collections import defaultdict
            by_designer: dict[str, list[str]] = defaultdict(list)
            wallet_map: dict[str, str] = {}
            for d7_nick, wallet, task_code, cost_usdt, _ps in rows:
                by_designer[d7_nick].append(f"{task_code} {cost_usdt:.2f}")
                wallet_map[d7_nick] = wallet

            for nick, task_lines in by_designer.items():
                from d7_bot.db import Designer as Des
                fake_designer = Des(
                    telegram_id=0,
                    username=None,
                    d7_nick=nick,
                    role="",
                    wallet=wallet_map[nick],
                )
                try:
                    await sheets.append_report_rows(fake_designer, yesterday.isoformat(), task_lines)
                except Exception as exc:
                    logger.error("Sheets append_report_rows failed for %s: %s", nick, exc)


def setup_scheduler(
    bot: Bot,
    db: Database,
    sheets: GoogleSheetsExporter,
    config: Config,
) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduler_job,
        trigger="cron",
        hour=config.report_hour_utc,
        minute=0,
        kwargs={"bot": bot, "db": db, "sheets": sheets, "config": config},
        id="daily_report",
        replace_existing=True,
    )
    logger.info(
        "Daily report scheduled at %02d:00 UTC.", config.report_hour_utc
    )
    return scheduler
