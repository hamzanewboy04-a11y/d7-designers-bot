from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from d7_bot.db import Database, Designer
from d7_bot.keyboards import (
    AVAILABLE_ROLES,
    build_confirm_keyboard,
    build_role_keyboard,
    main_menu_keyboard,
)
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="register")

# TRC20 validation: starts with 'T', length 34, base58 chars only
_BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRC20_RE = re.compile(rf"^T[{re.escape(_BASE58_CHARS)}]{{33}}$")

# Role value → display label mapping
_ROLE_LABELS: dict[str, str] = {value: label for label, value in AVAILABLE_ROLES}


def _is_valid_trc20(wallet: str) -> bool:
    return bool(_TRC20_RE.match(wallet))


class RegisterStates(StatesGroup):
    nick = State()
    role = State()
    wallet = State()
    confirm = State()


# ── /register entry point ──────────────────────────────────────────────────


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RegisterStates.nick)
    await message.answer(
        "📝 <b>Регистрация / обновление профиля</b>\n\n"
        "Введите ваш ник в D7:\n"
        "<i>Можно любые символы — кириллица, латиница, цифры (2–32 символа)</i>\n\n"
        "<i>В любой момент: /cancel — отменить</i>",
    )


# ── step 1: nick ───────────────────────────────────────────────────────────


@router.message(RegisterStates.nick)
async def step_nick(message: Message, state: FSMContext) -> None:
    nick = (message.text or "").strip()
    if len(nick) < 2 or len(nick) > 32:
        await message.answer(
            "❌ <b>Некорректный ник.</b>\n\n"
            "Длина: от 2 до 32 символов\n\n"
            "Попробуйте ещё раз:"
        )
        return
    await state.update_data(d7_nick=nick)
    await state.set_state(RegisterStates.role)
    await message.answer(
        f"✅ Ник: <b>{nick}</b>\n\n"
        "👔 <b>Выберите вашу роль:</b>",
        reply_markup=build_role_keyboard(),
    )


# ── step 2: role (inline buttons) ─────────────────────────────────────────


@router.callback_query(RegisterStates.role, F.data.startswith("role_select:"))
async def cb_role_select(callback: CallbackQuery, state: FSMContext) -> None:
    role_value = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    valid_values = {v for _, v in AVAILABLE_ROLES}
    if role_value not in valid_values:
        await callback.answer("❌ Неизвестная роль.")
        return

    role_label = _ROLE_LABELS.get(role_value, role_value)
    await state.update_data(role=role_value)
    await callback.answer(f"Выбрано: {role_label}")
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await state.set_state(RegisterStates.wallet)
    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ Роль: <b>{role_label}</b>\n\n"
        "💳 <b>Введите ваш TRC20-кошелёк USDT</b>\n\n"
        "<i>Начинается с «T», ровно 34 символа (base58)</i>"
    )


# ── step 3: wallet ─────────────────────────────────────────────────────────


@router.message(RegisterStates.wallet)
async def step_wallet(message: Message, state: FSMContext) -> None:
    wallet = (message.text or "").strip()
    if not _is_valid_trc20(wallet):
        await message.answer(
            "❌ <b>Некорректный TRC20-кошелёк.</b>\n\n"
            "Требования:\n"
            "• Начинается с буквы «T»\n"
            "• Ровно 34 символа\n"
            "• Только символы base58\n\n"
            "Проверьте адрес и попробуйте снова:"
        )
        return
    await state.update_data(wallet=wallet)

    data = await state.get_data()
    role_label = _ROLE_LABELS.get(data.get("role", ""), data.get("role", "—"))

    summary = (
        "📋 <b>Проверьте ваши данные:</b>\n\n"
        f"🏷 Ник: <code>{data['d7_nick']}</code>\n"
        f"👔 Роль: {role_label}\n"
        f"💳 Кошелёк: <code>{wallet}</code>\n\n"
        "Всё верно?"
    )
    await state.set_state(RegisterStates.confirm)
    await message.answer(
        summary,
        reply_markup=build_confirm_keyboard(),
    )


# ── step 4: confirm ────────────────────────────────────────────────────────


@router.callback_query(RegisterStates.confirm, F.data == "reg_confirm:yes")
async def cb_confirm_yes(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    sheets: GoogleSheetsExporter,
) -> None:
    data = await state.get_data()
    user = callback.from_user

    designer = Designer(
        telegram_id=user.id,
        username=user.username,
        d7_nick=data["d7_nick"],
        role=data.get("role", ""),
        wallet=data["wallet"],
    )
    await db.upsert_designer(designer)
    await state.clear()

    role_label = _ROLE_LABELS.get(designer.role, designer.role or "—")

    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.answer("✅ Профиль сохранён!")
    await callback.message.answer(  # type: ignore[union-attr]
        f"🎉 <b>Профиль {designer.d7_nick} успешно сохранён!</b>\n\n"
        f"Роль: {role_label}\n\n"
        f"Теперь вы можете сдавать отчёты 👇",
        reply_markup=main_menu_keyboard(),
    )
    logger.info("Designer registered/updated: %s (tg_id=%s)", designer.d7_nick, user.id)

    # Sync to Google Sheets
    if sheets.is_enabled:
        try:
            all_designers = await db.list_designers()
            await sheets.sync_designers(all_designers)
            logger.info("Sheets synced after designer update: %s", designer.d7_nick)
        except Exception as exc:
            logger.error("Sheets sync failed after registration: %s", exc)


@router.callback_query(RegisterStates.confirm, F.data == "reg_confirm:no")
async def cb_confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "✏️ Регистрация отменена.\n\n"
        "Начните заново: /register или нажмите кнопку меню 👇",
        reply_markup=main_menu_keyboard(),
    )
