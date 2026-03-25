from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from d7_bot.db import Database
from d7_bot.keyboards import (
    BTN_EDIT,
    BTN_PROFILE,
    BTN_REPORT,
    BTN_TASKS,
    MAIN_MENU_BUTTONS,
    main_menu_keyboard,
    period_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="common")


# ── /start ─────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    first_name = user.first_name or "дизайнер"
    designer = await db.get_designer(user.id)

    if designer:
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Я помогаю команде D7 вести учёт задач.\n\n"
            f"Добро пожаловать обратно, <b>{designer.d7_nick}</b>! 👇\n\n"
            f"Выберите действие из меню ниже или используйте команды:\n"
            f"• /report — сдать отчёт\n"
            f"• /me — мой профиль\n"
            f"• /myreports — мои задачи\n"
            f"• /register — обновить профиль\n"
            f"• /cancel — отменить текущее действие"
        )
    else:
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Я помогаю команде D7 вести учёт задач.\n\n"
            f"Для начала работы необходимо зарегистрироваться 👇\n\n"
            f"Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register"
        )

    await message.answer(text, reply_markup=main_menu_keyboard())


# ── /cancel ────────────────────────────────────────────────────────────────


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer(
            "ℹ️ Нечего отменять — вы не находитесь в процессе ввода данных.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await state.clear()
    await message.answer(
        "❌ Действие отменено.\n\nВыберите что-нибудь из меню 👇",
        reply_markup=main_menu_keyboard(),
    )


# ── /me ────────────────────────────────────────────────────────────────────


@router.message(Command("me"))
async def cmd_me(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ Вы ещё не зарегистрированы.\n\n"
            "Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(),
        )
        return

    formats_str = ", ".join(designer.formats) if designer.formats else "—"

    # Mask wallet: show first 4 and last 4 characters
    wallet = designer.wallet
    if len(wallet) > 10:
        wallet_display = f"{wallet[:4]}…{wallet[-4:]}"
    else:
        wallet_display = wallet

    # Get stats for 7 days
    stats = await db.get_designer_stats(user.id, days=7)
    task_count = stats["task_count"]
    total_usdt = stats["total_usdt"]

    tg_link = f"@{designer.username}" if designer.username else f"id{designer.telegram_id}"

    await message.answer(
        f"👤 <b>Профиль дизайнера</b>\n\n"
        f"🏷 Ник: <code>{designer.d7_nick}</code>\n"
        f"🔗 Telegram: {tg_link}\n"
        f"🎨 Форматы: {formats_str}\n"
        f"💳 Кошелёк: <code>{wallet_display}</code>\n\n"
        f"📊 Задач за 7 дней: <b>{task_count}</b>\n"
        f"💰 Сумма за 7 дней: <b>{total_usdt:.2f} USDT</b>",
        reply_markup=main_menu_keyboard(),
    )


# ── /myreports ─────────────────────────────────────────────────────────────


@router.message(Command("myreports"))
async def cmd_myreports(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ Вы ещё не зарегистрированы.\n\n"
            "Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "📋 <b>Выберите период для просмотра задач:</b>",
        reply_markup=period_keyboard(),
    )


@router.callback_query(F.data.startswith("period:"))
async def cb_period(callback: CallbackQuery, db: Database) -> None:
    user = callback.from_user
    if not user:
        await callback.answer()
        return

    days_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    try:
        days = int(days_str)
    except ValueError:
        days = 7

    designer = await db.get_designer(user.id)
    if not designer:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    rows = await db.list_tasks_by_designer(user.id, days=days)

    await callback.answer()

    if not rows:
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"📋 За последние <b>{days} дней</b> задач не найдено.\n\n"
            f"Сдайте первый отчёт через <b>«📝 Сдать отчёт»</b>",
        )
        await callback.message.answer(  # type: ignore[union-attr]
            "Выберите действие 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines = [f"📋 <b>Ваши задачи за {days} дней:</b>\n"]
    current_date: str | None = None
    day_total = 0.0
    grand_total = 0.0

    for report_date, task_code, cost_usdt in rows:
        if report_date != current_date:
            if current_date is not None:
                lines.append(f"  <i>Итого: {day_total:.2f} USDT</i>")
            current_date = report_date
            day_total = 0.0
            lines.append(f"\n📅 <b>{report_date}</b>")
        lines.append(f"  • <code>{task_code}</code> — {cost_usdt:.2f} USDT")
        day_total += cost_usdt
        grand_total += cost_usdt

    if current_date is not None:
        lines.append(f"  <i>Итого: {day_total:.2f} USDT</i>")

    lines.append(f"\n💰 <b>Всего за период: {grand_total:.2f} USDT</b>")

    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "Выберите действие 👇",
        reply_markup=main_menu_keyboard(),
    )


# ── Main menu button handlers ──────────────────────────────────────────────


@router.message(F.text == BTN_REPORT)
async def btn_report(message: Message, state: FSMContext, db: Database) -> None:
    """Trigger /report flow from main menu button."""
    from d7_bot.handlers.report import cmd_report
    await cmd_report(message, state, db)


@router.message(F.text == BTN_PROFILE)
async def btn_profile(message: Message, db: Database) -> None:
    """Trigger /me from main menu button."""
    await cmd_me(message, db)


@router.message(F.text == BTN_TASKS)
async def btn_tasks(message: Message, db: Database) -> None:
    """Trigger /myreports from main menu button."""
    await cmd_myreports(message, db)


@router.message(F.text == BTN_EDIT)
async def btn_edit(message: Message, state: FSMContext) -> None:
    """Trigger /register from main menu button."""
    from d7_bot.handlers.register import cmd_register
    await cmd_register(message, state)


# ── Fallback for unknown messages ──────────────────────────────────────────


@router.message()
async def fallback_handler(message: Message, state: FSMContext) -> None:
    """Catch all messages that aren't handled by any other router."""
    current = await state.get_state()
    if current is not None:
        # User is in some FSM flow — don't interfere, just ignore
        return

    await message.answer(
        "🤔 Я не понял эту команду.\n\n"
        "Воспользуйтесь кнопками меню ниже 👇\n\n"
        "Или введите одну из команд:\n"
        "• /report — сдать отчёт\n"
        "• /me — мой профиль\n"
        "• /myreports — мои задачи\n"
        "• /register — зарегистрироваться / обновить профиль\n"
        "• /cancel — отменить текущее действие",
        reply_markup=main_menu_keyboard(),
    )
