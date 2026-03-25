from __future__ import annotations

import logging
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d7_bot.config import Config
from d7_bot.db import Database

logger = logging.getLogger(__name__)
router = Router(name="admin")


async def _check_admin(message: Message, db: Database, config: Config) -> bool:
    """Reply with error and return False if user is not admin."""
    user = message.from_user
    if not user:
        return False
    if not await db.is_admin(user.id, config.admin_ids):
        await message.answer("⛔ Недостаточно прав.")
        return False
    return True


# ── /addadmin ──────────────────────────────────────────────────────────────


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /addadmin <telegram_id>\n"
            "Пример: `/addadmin 123456789`",
            parse_mode="Markdown",
        )
        return

    new_admin_id = int(args[1].strip())
    current_admins = await db.list_admins()

    if new_admin_id in current_admins or new_admin_id in config.admin_ids:
        await message.answer(f"ℹ️ Пользователь `{new_admin_id}` уже является администратором.")
        return

    await db.add_admin(new_admin_id)
    logger.info("Admin added: %s (by %s)", new_admin_id, message.from_user.id)  # type: ignore[union-attr]
    await message.answer(f"✅ Пользователь `{new_admin_id}` добавлен как администратор.", parse_mode="Markdown")


# ── /listdesigners ─────────────────────────────────────────────────────────


@router.message(Command("listdesigners"))
async def cmd_listdesigners(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    designers = await db.list_designers()
    if not designers:
        await message.answer("Дизайнеров пока нет.")
        return

    lines = [f"👥 *Список дизайнеров ({len(designers)}):*\n"]
    for d in designers:
        formats_str = ", ".join(d.formats) if d.formats else "—"
        tg_link = f"@{d.username}" if d.username else f"id{d.telegram_id}"
        lines.append(
            f"• *{d.d7_nick}* ({tg_link})\n"
            f"  Форматы: {formats_str}\n"
            f"  Кошелёк: `{d.wallet}`"
        )

    # Split into chunks to avoid Telegram message size limit
    chunk: list[str] = [lines[0]]
    for line in lines[1:]:
        if sum(len(l) for l in chunk) + len(line) > 3800:
            await message.answer("\n".join(chunk), parse_mode="Markdown")
            chunk = []
        chunk.append(line)
    if chunk:
        await message.answer("\n".join(chunk), parse_mode="Markdown")


# ── /adminreport ───────────────────────────────────────────────────────────


@router.message(Command("adminreport"))
async def cmd_adminreport(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        # Default: yesterday
        report_date = date.today().replace(day=date.today().day - 1) if date.today().day > 1 else date.today()
        # simpler:
        from datetime import timedelta
        report_date = date.today() - timedelta(days=1)
    else:
        date_str = args[1].strip()
        try:
            report_date = date.fromisoformat(date_str)
        except ValueError:
            await message.answer(
                "❌ Неверный формат даты. Используйте YYYY-MM-DD.\n"
                "Пример: `/adminreport 2024-01-15`",
                parse_mode="Markdown",
            )
            return

    rows = await db.list_tasks_by_date(report_date)
    if not rows:
        await message.answer(f"За *{report_date.isoformat()}* задач не найдено.", parse_mode="Markdown")
        return

    lines: list[str] = [f"📊 *Отчёт за {report_date.isoformat()}*\n"]
    current_nick: str | None = None
    day_total = 0.0
    total = 0.0

    for d7_nick, wallet, task_code, cost_usdt in rows:
        if d7_nick != current_nick:
            if current_nick is not None:
                lines.append(f"  _Итого: {day_total:.2f} USDT_")
            current_nick = d7_nick
            day_total = 0.0
            lines.append(f"\n👤 *{d7_nick}* (`{wallet}`)")
        lines.append(f"  • `{task_code}` — {cost_usdt:.2f} USDT")
        day_total += cost_usdt
        total += cost_usdt

    if current_nick is not None:
        lines.append(f"  _Итого: {day_total:.2f} USDT_")

    lines.append(f"\n💰 *Итого за день: {total:.2f} USDT*")
    await message.answer("\n".join(lines), parse_mode="Markdown")
