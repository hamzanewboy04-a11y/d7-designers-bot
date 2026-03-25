from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from d7_bot.db import Database

logger = logging.getLogger(__name__)
router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if designer:
        await message.answer(
            f"👋 С возвращением, *{designer.d7_nick}*!\n\n"
            "Доступные команды:\n"
            "• /report — сдать отчёт по задачам\n"
            "• /myreports — мои задачи за 7 дней\n"
            "• /me — мой профиль\n"
            "• /register — обновить профиль\n"
            "• /cancel — отменить текущее действие",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "👋 Привет! Я бот для учёта задач дизайнеров *D7*.\n\n"
            "Для начала зарегистрируйся: /register",
            parse_mode="Markdown",
        )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять. Вы не в процессе ввода данных.")
        return
    await state.clear()
    await message.answer("❌ Действие отменено. Вы вернулись в главное меню.")


@router.message(Command("me"))
async def cmd_me(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer("Вы не зарегистрированы. Используйте /register.")
        return

    formats_str = ", ".join(designer.formats) if designer.formats else "—"
    portfolio_str = "\n".join(f"  • {p}" for p in designer.portfolio) if designer.portfolio else "  —"

    await message.answer(
        f"👤 *Ваш профиль*\n\n"
        f"Ник: `{designer.d7_nick}`\n"
        f"Опыт: {designer.experience}\n"
        f"Форматы: {formats_str}\n"
        f"Кошелёк: `{designer.wallet}`\n"
        f"Портфолио:\n{portfolio_str}",
        parse_mode="Markdown",
    )


@router.message(Command("myreports"))
async def cmd_myreports(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer("Вы не зарегистрированы. Используйте /register.")
        return

    rows = await db.list_tasks_by_designer(user.id, days=7)
    if not rows:
        await message.answer("За последние 7 дней задач не найдено.")
        return

    lines = ["📋 *Ваши задачи за последние 7 дней:*\n"]
    current_date: str | None = None
    day_total = 0.0
    grand_total = 0.0

    for report_date, task_code, cost_usdt in rows:
        if report_date != current_date:
            if current_date is not None:
                lines.append(f"  _Итого: {day_total:.2f} USDT_")
            current_date = report_date
            day_total = 0.0
            lines.append(f"\n📅 *{report_date}*")
        lines.append(f"  • `{task_code}` — {cost_usdt:.2f} USDT")
        day_total += cost_usdt
        grand_total += cost_usdt

    if current_date is not None:
        lines.append(f"  _Итого: {day_total:.2f} USDT_")

    lines.append(f"\n💰 *Всего за период: {grand_total:.2f} USDT*")
    await message.answer("\n".join(lines), parse_mode="Markdown")
