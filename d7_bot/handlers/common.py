from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from d7_bot.config import Config
from d7_bot.db import Database
from d7_bot.keyboards import (
    BTN_ADMIN_DESIGNERS,
    BTN_ADMIN_REPORT,
    BTN_EDIT,
    BTN_PROFILE,
    BTN_REPORT,
    BTN_TASKS,
    main_menu_keyboard,
    period_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="common")


# ── /start ─────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database, config: Config) -> None:
    user = message.from_user
    if not user:
        return

    first_name = user.first_name or "дизайнер"
    designer = await db.get_designer(user.id)
    is_admin = await db.is_admin(user.id, config.admin_ids)

    if designer:
        admin_hint = "\n• /listdesigners — все дизайнеры\n• /adminreport — отчёт за день" if is_admin else ""
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Я помогаю команде D7 вести учёт задач.\n\n"
            f"Добро пожаловать обратно, <b>{designer.d7_nick}</b>! 👇\n\n"
            f"Команды:\n"
            f"• /report — сдать отчёт\n"
            f"• /me — мой профиль\n"
            f"• /myreports — мои задачи\n"
            f"• /register — обновить профиль"
            f"{admin_hint}"
        )
    else:
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Я помогаю команде D7 вести учёт задач.\n\n"
            f"Для начала работы необходимо зарегистрироваться 👇\n\n"
            f"Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register"
        )

    await message.answer(text, reply_markup=main_menu_keyboard(is_admin=is_admin))


# ── /cancel ────────────────────────────────────────────────────────────────


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    user = message.from_user
    is_admin = await db.is_admin(user.id, config.admin_ids) if user else False
    current = await state.get_state()
    if current is None:
        await message.answer(
            "ℹ️ Нечего отменять — вы не находитесь в процессе ввода данных.",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        return
    await state.clear()
    await message.answer(
        "❌ Действие отменено.\n\nВыберите что-нибудь из меню 👇",
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )


# ── /me ────────────────────────────────────────────────────────────────────


@router.message(Command("me"))
async def cmd_me(message: Message, db: Database, config: Config) -> None:
    user = message.from_user
    if not user:
        return

    is_admin = await db.is_admin(user.id, config.admin_ids)
    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ Вы ещё не зарегистрированы.\n\n"
            "Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        return

    formats_str = ", ".join(designer.formats) if designer.formats else "—"
    wallet = designer.wallet
    wallet_display = f"{wallet[:4]}…{wallet[-4:]}" if len(wallet) > 10 else wallet

    stats = await db.get_designer_stats(user.id, days=7)
    tg_link = f"@{designer.username}" if designer.username else f"id{designer.telegram_id}"
    admin_badge = "\n\n🔐 <b>Вы администратор</b>" if is_admin else ""

    await message.answer(
        f"👤 <b>Профиль дизайнера</b>\n\n"
        f"🏷 Ник: <code>{designer.d7_nick}</code>\n"
        f"🔗 Telegram: {tg_link}\n"
        f"🎨 Форматы: {formats_str}\n"
        f"💳 Кошелёк: <code>{wallet_display}</code>\n\n"
        f"📊 Задач за 7 дней: <b>{stats['task_count']}</b>\n"
        f"💰 Сумма за 7 дней: <b>{stats['total_usdt']:.2f} USDT</b>"
        f"{admin_badge}",
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )


# ── /myreports ─────────────────────────────────────────────────────────────


@router.message(Command("myreports"))
async def cmd_myreports(message: Message, db: Database, config: Config) -> None:
    user = message.from_user
    if not user:
        return

    is_admin = await db.is_admin(user.id, config.admin_ids)
    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ Вы ещё не зарегистрированы.\n\n"
            "Нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        return

    await message.answer(
        "📋 <b>Выберите период для просмотра задач:</b>",
        reply_markup=period_keyboard(),
    )


@router.callback_query(F.data.startswith("period:"))
async def cb_period(callback: CallbackQuery, db: Database, config: Config) -> None:
    user = callback.from_user
    if not user:
        await callback.answer()
        return

    days_str = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    try:
        days = int(days_str)
    except ValueError:
        days = 7

    is_admin = await db.is_admin(user.id, config.admin_ids)
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
            reply_markup=main_menu_keyboard(is_admin=is_admin),
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

    await callback.message.edit_text("\n".join(lines))  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Выберите действие 👇",
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )


# ── Main menu button handlers ──────────────────────────────────────────────


@router.message(F.text == BTN_REPORT)
async def btn_report(message: Message, state: FSMContext, db: Database) -> None:
    from d7_bot.handlers.report import cmd_report
    await cmd_report(message, state, db)


@router.message(F.text == BTN_PROFILE)
async def btn_profile(message: Message, db: Database, config: Config) -> None:
    await cmd_me(message, db, config)


@router.message(F.text == BTN_TASKS)
async def btn_tasks(message: Message, db: Database, config: Config) -> None:
    await cmd_myreports(message, db, config)


@router.message(F.text == BTN_EDIT)
async def btn_edit(message: Message, state: FSMContext) -> None:
    from d7_bot.handlers.register import cmd_register
    await cmd_register(message, state)


@router.message(F.text == BTN_ADMIN_DESIGNERS)
async def btn_admin_designers(message: Message, db: Database, config: Config) -> None:
    from d7_bot.handlers.admin import cmd_listdesigners
    await cmd_listdesigners(message, db, config)


@router.message(F.text == BTN_ADMIN_REPORT)
async def btn_admin_report(message: Message, db: Database, config: Config) -> None:
    from d7_bot.handlers.admin import cmd_adminreport
    await cmd_adminreport(message, db, config)


# ── Fallback ───────────────────────────────────────────────────────────────


@router.message()
async def fallback_handler(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    current = await state.get_state()
    if current is not None:
        return

    user = message.from_user
    is_admin = await db.is_admin(user.id, config.admin_ids) if user else False

    await message.answer(
        "🤔 Я не понял эту команду.\n\n"
        "Воспользуйтесь кнопками меню ниже 👇",
        reply_markup=main_menu_keyboard(is_admin=is_admin),
    )
