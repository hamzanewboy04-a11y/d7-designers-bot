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
    AVAILABLE_FORMATS,
    build_confirm_keyboard,
    build_formats_keyboard,
    main_menu_keyboard,
)
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="register")

# TRC20 validation: starts with 'T', length 34, base58 chars only
_BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRC20_RE = re.compile(rf"^T[{re.escape(_BASE58_CHARS)}]{{33}}$")


def _is_valid_trc20(wallet: str) -> bool:
    return bool(_TRC20_RE.match(wallet))


class RegisterStates(StatesGroup):
    nick = State()
    formats = State()
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
    await state.update_data(d7_nick=nick, selected_formats=[])
    await state.set_state(RegisterStates.formats)
    await message.answer(
        f"✅ Ник: <b>{nick}</b>\n\n"
        "🎨 <b>Выберите форматы работ</b>\n\n"
        "Нажимайте на кнопки для выбора/отмены.\n"
        "Когда закончите — нажмите <b>«✅ Готово»</b>:",
        reply_markup=build_formats_keyboard([]),
    )


# ── step 2: formats (inline toggle) ───────────────────────────────────────


@router.callback_query(RegisterStates.formats, F.data.startswith("fmt_toggle:"))
async def cb_fmt_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    fmt = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    if fmt not in AVAILABLE_FORMATS:
        await callback.answer("❌ Неизвестный формат.")
        return

    data = await state.get_data()
    selected: list[str] = data.get("selected_formats", [])

    if fmt in selected:
        selected.remove(fmt)
        await callback.answer(f"☐ {fmt} убран")
    else:
        selected.append(fmt)
        await callback.answer(f"✅ {fmt} добавлен")

    await state.update_data(selected_formats=selected)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=build_formats_keyboard(selected)
    )


@router.callback_query(RegisterStates.formats, F.data == "fmt_done")
async def cb_fmt_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list[str] = data.get("selected_formats", [])
    if not selected:
        await callback.answer("⚠️ Выберите хотя бы один формат!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await state.set_state(RegisterStates.wallet)

    formats_display = " • ".join(selected)
    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ Выбрано форматов: <b>{len(selected)}</b>\n"
        f"<i>{formats_display}</i>\n\n"
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

    # Build summary and ask for confirmation
    data = await state.get_data()
    formats_str = ", ".join(data["selected_formats"])

    # Mask wallet for display
    wallet_display = f"{wallet[:4]}…{wallet[-4:]}"

    summary = (
        "📋 <b>Проверьте ваши данные:</b>\n\n"
        f"🏷 Ник: <code>{data['d7_nick']}</code>\n"
        f"🎨 Форматы: {formats_str}\n"
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
        formats=data["selected_formats"],
        wallet=data["wallet"],
    )
    await db.upsert_designer(designer)
    await state.clear()

    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.answer("✅ Профиль сохранён!")
    await callback.message.answer(  # type: ignore[union-attr]
        f"🎉 <b>Профиль {designer.d7_nick} успешно сохранён!</b>\n\n"
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
