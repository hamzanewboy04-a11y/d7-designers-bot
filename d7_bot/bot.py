from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from d7_bot.config import load_config
from d7_bot.db import Database
from d7_bot.handlers import admin, common, pm, register, report
from d7_bot.scheduler import setup_scheduler
from d7_bot.sheets import GoogleSheetsExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()

    # ── Database ───────────────────────────────────────────────────────────
    db = Database(config.db_path)
    await db.init()
    logger.info("Database initialised at %s", config.db_path)

    # Seed initial admins from config into DB
    for admin_id in config.admin_ids:
        await db.add_admin(admin_id)

    # ── Google Sheets ──────────────────────────────────────────────────────
    sheets = GoogleSheetsExporter(config.google_sheet_id, config.google_service_account_json)
    if sheets.is_enabled:
        logger.info("Google Sheets integration enabled (sheet_id=%s)", config.google_sheet_id)
        # Sync designers on startup to keep the sheet up-to-date
        try:
            designers = await db.list_designers()
            await sheets.sync_designers(designers)
            logger.info("Sheets: initial sync complete (%d designers)", len(designers))
        except Exception as exc:
            logger.error("Sheets: initial sync failed (bot will continue): %s", exc)
    else:
        logger.info("Google Sheets integration disabled.")

    # ── Bot & Dispatcher ───────────────────────────────────────────────────
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Inject dependencies via workflow_data
    dp["db"] = db
    dp["sheets"] = sheets
    dp["config"] = config

    # ── Routers ────────────────────────────────────────────────────────────
    # Order matters: specific routers first, fallback (common) last
    dp.include_router(register.router)
    dp.include_router(report.router)
    dp.include_router(pm.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)  # common must be last (contains fallback handler)

    # ── Scheduler ─────────────────────────────────────────────────────────
    scheduler = setup_scheduler(bot, db, sheets, config)
    scheduler.start()
    logger.info("Scheduler started.")

    # ── Start polling ──────────────────────────────────────────────────────
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")
