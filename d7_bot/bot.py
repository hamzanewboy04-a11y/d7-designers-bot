from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from d7_bot.config import load_config
from d7_bot.db import Database
from d7_bot.handlers import admin, common, pm, register, report, reviewer_v2
from d7_bot.scheduler import setup_scheduler
from d7_bot.sheets import GoogleSheetsExporter
from services.reviewer_domain import ReviewerDomainService
from services.smm_domain import SmmDomainService
from storage.repositories.reviewer_domain import PostgresReviewerDomainRepository
from storage.repositories.smm_domain import PostgresSmmDomainRepository
from storage.session import create_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _sync_designers_with_retry(db: Database, sheets: GoogleSheetsExporter) -> bool:
    designers = await db.list_designers()
    attempts = 3
    delays = [1, 3]
    for attempt in range(1, attempts + 1):
        try:
            await sheets.sync_designers(designers)
            logger.info("Sheets: initial sync complete (%d designers)", len(designers))
            return True
        except Exception as exc:
            if attempt >= attempts:
                logger.error("Sheets: initial sync failed after %d attempts (bot will continue): %s", attempt, exc)
                return False
            delay = delays[min(attempt - 1, len(delays) - 1)]
            logger.warning(
                "Sheets: initial sync attempt %d/%d failed: %s. Retrying in %ss...",
                attempt,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    return False


async def main() -> None:
    config = load_config()
    pg_engine = None

    # ── Database ───────────────────────────────────────────────────────────
    db = Database(config.db_path)
    await db.init()
    logger.info("Database initialised at %s", config.db_path)

    # Seed initial admins from config into DB
    for admin_id in config.admin_ids:
        await db.add_admin(admin_id)

    reviewer_domain = ReviewerDomainService(db)
    smm_domain = SmmDomainService(db)
    reviewer_backend_name = "sqlite"
    smm_backend_name = "sqlite"
    if config.database_url:
        try:
            pg_engine, _pg_session_factory = create_session_factory(config.database_url)
            reviewer_domain = ReviewerDomainService(
                PostgresReviewerDomainRepository(_pg_session_factory, admin_fallback=db)
            )
            smm_domain = SmmDomainService(
                PostgresSmmDomainRepository(_pg_session_factory, admin_fallback=db)
            )
            reviewer_backend_name = "postgres"
            smm_backend_name = "postgres"
            logger.info("Reviewer domain configured to use PostgreSQL backend.")
            logger.info("SMM domain configured to use PostgreSQL backend.")
        except Exception as exc:
            logger.warning("Could not initialize PostgreSQL domain backends, falling back to SQLite: %s", exc)
    else:
        logger.info("DATABASE_URL is not configured; reviewer and SMM domains will use SQLite fallback.")

    logger.info(
        "Runtime storage mode: reviewer=%s, smm=%s, legacy_designer_admin=sqlite",
        reviewer_backend_name,
        smm_backend_name,
    )

    # ── Google Sheets ──────────────────────────────────────────────────────
    sheets = GoogleSheetsExporter(config.google_sheet_id, config.google_service_account_json)
    if sheets.is_enabled:
        logger.info("Google Sheets integration enabled (sheet_id=%s)", config.google_sheet_id)
        await _sync_designers_with_retry(db, sheets)
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
    dp["reviewer_domain"] = reviewer_domain
    dp["smm_domain"] = smm_domain
    dp["sheets"] = sheets
    dp["config"] = config

    # ── Routers ────────────────────────────────────────────────────────────
    # Order matters: specific routers first, fallback (common) last
    dp.include_router(register.router)
    dp.include_router(report.router)
    dp.include_router(reviewer_v2.router)
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
        if pg_engine is not None:
            await pg_engine.dispose()
        logger.info("Bot stopped.")
