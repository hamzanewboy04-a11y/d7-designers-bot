from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from d7_bot.config import Config
from d7_bot.db import Database
from d7_bot.keyboards import (
    BTN_ADMIN_HUB,
    BTN_EDIT,
    BTN_HELP,
    BTN_PROFILE,
    BTN_REPORT,
    BTN_TASKS,
    ROLE_LABELS,
    admin_hub_keyboard,
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

    first_name = user.first_name or "сотрудник"
    designer = await db.get_designer(user.id)
    is_admin = await db.is_admin(user.id, config.admin_ids)

    if designer:
        role_label = ROLE_LABELS.get(designer.role or "", designer.role or "сотрудник")
        if designer.role == "designer":
            role_hint = (
                "<b>Что вы можете делать здесь:</b>\n"
                "• сдавать ежедневные отчёты\n"
                "• смотреть свои последние задачи\n"
                "• обновлять профиль и кошелёк\n\n"
                "<b>С чего начать:</b>\n"
                "1. Нажмите <b>📝 Сдать отчёт</b>\n"
                "2. Проверьте себя в <b>👤 Мой профиль</b>\n"
                "3. Если что-то непонятно — откройте <b>❓ Помощь</b>"
            )
        elif designer.role == "reviewer":
            role_hint = (
                "<b>Что вы можете делать здесь:</b>\n"
                "• отправлять reviewer-отчёты\n"
                "• следить за своим профилем\n"
                "• понимать, что произойдёт после отправки отчёта\n\n"
                "<b>Как это работает:</b>\n"
                "Ваш отчёт уходит на проверку PM. После подтверждения он попадает в выплату."
            )
        elif designer.role == "smm":
            role_hint = (
                "<b>Что вы можете делать здесь:</b>\n"
                "• смотреть свой профиль\n"
                "• уточнять роль и рабочие данные\n\n"
                "<b>Важно:</b>\n"
                "SMM-записи и выплаты обычно ведутся через PM. Если есть вопросы по начислениям — откройте <b>❓ Помощь</b>."
            )
        elif designer.role == "project_manager":
            role_hint = (
                "<b>Что вы можете делать здесь:</b>\n"
                "• работать с reviewer-очередью\n"
                "• вести SMM-назначения\n"
                "• управлять выплатами\n\n"
                "Для операционных действий используйте <b>🛠 Админка</b> и <b>❓ Помощь</b>."
            )
        else:
            role_hint = "Используйте меню ниже и раздел <b>❓ Помощь</b>, если хотите быстро понять, что к чему."

        admin_hint = (
            "\n\n<b>Для админа дополнительно:</b>\n"
            "• <b>🛠 Админка</b> — панель управления\n"
            "• в вебке есть разделы по выплатам, сотрудникам и отчётам"
        ) if is_admin else ""
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Вы в системе как <b>{designer.d7_nick}</b> (<b>{role_label}</b>).\n\n"
            f"{role_hint}\n\n"
            f"<b>Основные действия:</b>\n"
            f"• /report — сдать отчёт\n"
            f"• /me — мой профиль\n"
            f"• /myreports — мои задачи\n"
            f"• /register — обновить профиль\n"
            f"• /help — помощь и объяснения"
            f"{admin_hint}"
        )
    else:
        text = (
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"Я помогаю команде D7 вести отчётность, роли и выплаты.\n\n"
            f"<b>Что нужно сделать сначала:</b>\n"
            f"1. Зарегистрироваться\n"
            f"2. Указать свою роль и кошелёк\n"
            f"3. После этого появятся нужные вам действия\n\n"
            f"Сначала заполните профиль: нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register\n"
            f"Если хотите понять, как всё устроено — откройте /help"
        )

    await message.answer(text, reply_markup=main_menu_keyboard(is_admin=is_admin))


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database, config: Config) -> None:
    user = message.from_user
    if not user:
        return

    is_admin = await db.is_admin(user.id, config.admin_ids)
    designer = await db.get_designer(user.id)

    if not designer:
        text = (
            "<b>❓ Как пользоваться ботом</b>\n\n"
            "Сначала нужно зарегистрироваться: /register\n\n"
            "После регистрации вы сможете:\n"
            "• сдавать отчёты\n"
            "• смотреть профиль\n"
            "• видеть свои данные\n\n"
            "Если вы не уверены, какая у вас роль, уточните у менеджера или администратора."
        )
    elif designer.role == "designer":
        text = (
            "<b>❓ Помощь для дизайнера</b>\n\n"
            "<b>Что делать чаще всего:</b>\n"
            "• <b>📝 Сдать отчёт</b> — отправить задачи за день\n"
            "• <b>📋 Мои задачи</b> — посмотреть последние записи\n"
            "• <b>👤 Мой профиль</b> — проверить роль и кошелёк\n\n"
            "<b>Как работает выплата:</b>\n"
            "После отправки отчёты попадают в систему оплаты. Статус зависит от проверки и обработки администратором.\n\n"
            "<b>Если ошиблись:</b>\n"
            "Обратитесь к менеджеру или администратору и не отправляйте дубликаты без необходимости."
        )
    elif designer.role == "reviewer":
        text = (
            "<b>❓ Помощь для отзовика</b>\n\n"
            "<b>Как работает reviewer flow:</b>\n"
            "1. Вы отправляете отчёт\n"
            "2. PM проверяет его\n"
            "3. После подтверждения отчёт попадает в batch на выплату\n\n"
            "<b>Важно:</b>\n"
            "Статусы могут быть submitted, verified или rejected. Если отчёт отклонён, обычно нужен комментарий или исправление."
        )
    elif designer.role == "smm":
        text = (
            "<b>❓ Помощь для SMM</b>\n\n"
            "SMM-назначения и дневные записи обычно ведутся через PM.\n\n"
            "<b>Что важно проверять:</b>\n"
            "• ваш профиль\n"
            "• корректность роли\n"
            "• актуальность кошелька\n\n"
            "Если есть вопрос по начислениям или активностям, лучше уточнять у PM."
        )
    else:
        text = (
            "<b>❓ Помощь для PM / администратора</b>\n\n"
            "<b>Что доступно:</b>\n"
            "• reviewer-очередь\n"
            "• создание и обработка batch'ей\n"
            "• SMM-назначения\n"
            "• legacy-отчёты и история выплат\n\n"
            "Для ручного управления используйте команды администратора и веб-панель."
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
            "ℹ️ Сейчас нечего отменять — вы не находитесь в процессе ввода данных.",
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
            "Сначала заполните профиль: нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        return

    role_str = designer.role if designer.role else "—"
    wallet = designer.wallet
    wallet_display = f"{wallet[:4]}…{wallet[-4:]}" if len(wallet) > 10 else wallet

    stats = await db.get_designer_stats(user.id, days=7)
    tg_link = f"@{designer.username}" if designer.username else f"id{designer.telegram_id}"
    admin_badge = "\n\n🔐 <b>Вы администратор</b>" if is_admin else ""

    await message.answer(
        f"👤 <b>Профиль сотрудника</b>\n\n"
        f"🏷 Ник: <code>{designer.d7_nick}</code>\n"
        f"🔗 Telegram: {tg_link}\n"
        f"👔 Роль: {role_str}\n"
        f"💳 Кошелёк: <code>{wallet_display}</code>\n\n"
        f"📊 Задач за 7 дней: <b>{stats['task_count']}</b>\n"
        f"💰 Сумма за 7 дней: <b>{stats['total_usdt']:.2f} USDT</b>\n\n"
        f"<b>Что можно сделать дальше:</b>\n"
        f"• <b>📝 Сдать отчёт</b> — если хотите добавить новые задачи\n"
        f"• <b>📋 Мои задачи</b> — чтобы посмотреть последние записи\n"
        f"• <b>✏️ Редактировать профиль</b> — если нужно обновить роль или кошелёк"
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
            "Сначала заполните профиль: нажмите <b>«✏️ Редактировать профиль»</b> или используйте /register",
            reply_markup=main_menu_keyboard(is_admin=is_admin),
        )
        return

    await message.answer(
        "📋 <b>Мои задачи</b>\n\n"
        "Здесь можно посмотреть свои последние отчёты и понять, сколько задач и на какую сумму уже зафиксировано.\n\n"
        "Выберите период:",
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
            f"Сдайте первый отчёт через <b>«📝 Сдать отчёт»</b>. После этого он появится здесь.",
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
    lines.append("\n<b>Что это значит:</b> здесь показаны ваши последние принятые задачи за выбранный период.")

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


@router.message(F.text == BTN_HELP)
async def btn_help(message: Message, db: Database, config: Config) -> None:
    await cmd_help(message, db, config)


# ── v8: Admin hub button handler ───────────────────────────────────────────


@router.message(F.text == BTN_ADMIN_HUB)
async def btn_admin_hub(message: Message, db: Database, config: Config) -> None:
    user = message.from_user
    if not user:
        return
    if not await db.is_admin(user.id, config.admin_ids):
        await message.answer("⛔ Недостаточно прав.")
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=admin_hub_keyboard(),
    )


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
