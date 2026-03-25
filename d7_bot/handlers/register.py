from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from d7_bot.db import Database, Designer
from d7_bot.keyboards import AVAILABLE_FORMATS, build_confirm_keyboard, build_formats_keyboard

logger = logging.getLogger(__name__)
router = Router(name="register")

# TRC20 validation: starts with 'T', length 34, base58 chars only
_BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRC20_RE = re.compile(rf"^T[{re.escape(_BASE58_CHARS)}]{{33}}$")


def _is_valid_trc20(wallet: str) -> bool:
    return bool(_TRC20_RE.match(wallet))


class RegisterStates(StatesGroup):
    nick = State()
    experience = State()
    formats = State()
    portfolio = State()
    wallet = State()
    confirm = State()


# ── /register entry point ──────────────────────────────────────────────────


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RegisterStates.nick)
    await message.answer(
        "📝 *Регистрация дизайнера*\n\n"
        "Введите ваш ник в D7 (латиница, цифры, подчёркивание, 3–32 символа):\n\n"
        "_В любой момент: /cancel — отменить_",
        parse_mode="Markdown",
    )


# ── step 1: nick ───────────────────────────────────────────────────────────


@router.message(RegisterStates.nick)
async def step_nick(message: Message, state: FSMContext) -> None:
    nick = (message.text or "").strip()
    if not re.match(r"^[\w]{3,32}$", nick):
        await message.answer(
            "❌ Некорректный ник. Используйте латиницу, цифры, подчёркивание (3–32 символа)."
        )
        return
    await state.update_data(d7_nick=nick)
    await state.set_state(RegisterStates.experience)
    await message.answer(
        "📋 Укажите ваш опыт работы дизайнером (например: «3 года», «6 месяцев»):"
    )


# ── step 2: experience ─────────────────────────────────────────────────────


@router.message(RegisterStates.experience)
async def step_experience(message: Message, state: FSMContext) -> None:
    experience = (message.text or "").strip()
    if len(experience) < 2 or len(experience) > 100:
        await message.answer("❌ Слишком короткое или длинное описание. Попробуйте ещё раз.")
        return
    await state.update_data(experience=experience, selected_formats=[])
    await state.set_state(RegisterStates.formats)
    await message.answer(
        "🎨 Выберите форматы работ (нажимайте кнопки для включения/выключения).\n"
        "Когда закончите, нажмите «Готово ➡️»:",
        reply_markup=build_formats_keyboard([]),
    )


# ── step 3: formats (inline toggle) ───────────────────────────────────────


@router.callback_query(RegisterStates.formats, F.data.startswith("fmt_toggle:"))
async def cb_fmt_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    fmt = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    if fmt not in AVAILABLE_FORMATS:
        await callback.answer("Неизвестный формат.")
        return

    data = await state.get_data()
    selected: list[str] = data.get("selected_formats", [])

    if fmt in selected:
        selected.remove(fmt)
    else:
        selected.append(fmt)

    await state.update_data(selected_formats=selected)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=build_formats_keyboard(selected)
    )
    await callback.answer()


@router.callback_query(RegisterStates.formats, F.data == "fmt_done")
async def cb_fmt_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list[str] = data.get("selected_formats", [])
    if not selected:
        await callback.answer("Выберите хотя бы один формат!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await state.set_state(RegisterStates.portfolio)
    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ Выбрано форматов: {len(selected)}\n\n"
        "🔗 Введите ссылки на ваше портфолио (каждая с новой строки).\n"
        "Можно указать Behance, Dribbble, личный сайт и т.д.:"
    )


# ── step 4: portfolio ──────────────────────────────────────────────────────


@router.message(RegisterStates.portfolio)
async def step_portfolio(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    portfolio = [line.strip() for line in raw.splitlines() if line.strip()]
    if not portfolio:
        await message.answer("❌ Укажите хотя бы одну ссылку на портфолио.")
        return
    await state.update_data(portfolio=portfolio)
    await state.set_state(RegisterStates.wallet)
    await message.answer(
        "💳 Введите ваш TRC20-кошелёк USDT\n"
        "_(начинается с T, ровно 34 символа, base58)_:",
        parse_mode="Markdown",
    )


# ── step 5: wallet ─────────────────────────────────────────────────────────


@router.message(RegisterStates.wallet)
async def step_wallet(message: Message, state: FSMContext) -> None:
    wallet = (message.text or "").strip()
    if not _is_valid_trc20(wallet):
        await message.answer(
            "❌ Некорректный TRC20-кошелёк.\n"
            "Должен начинаться с «T», содержать ровно 34 символа base58.\n"
            "Проверьте адрес и попробуйте снова:"
        )
        return
    await state.update_data(wallet=wallet)

    # Build summary and ask for confirmation
    data = await state.get_data()
    formats_str = ", ".join(data["selected_formats"])
    portfolio_str = "\n".join(f"  • {p}" for p in data["portfolio"])

    summary = (
        "📋 *Проверьте ваши данные:*\n\n"
        f"Ник: `{data['d7_nick']}`\n"
        f"Опыт: {data['experience']}\n"
        f"Форматы: {formats_str}\n"
        f"Портфолио:\n{portfolio_str}\n"
        f"Кошелёк: `{wallet}`\n\n"
        "Всё верно?"
    )
    await state.set_state(RegisterStates.confirm)
    await message.answer(
        summary,
        parse_mode="Markdown",
        reply_markup=build_confirm_keyboard(),
    )


# ── step 6: confirm ────────────────────────────────────────────────────────


@router.callback_query(RegisterStates.confirm, F.data == "reg_confirm:yes")
async def cb_confirm_yes(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    user = callback.from_user

    designer = Designer(
        telegram_id=user.id,
        username=user.username,
        d7_nick=data["d7_nick"],
        experience=data["experience"],
        formats=data["selected_formats"],
        portfolio=data["portfolio"],
        wallet=data["wallet"],
    )
    await db.upsert_designer(designer)
    await state.clear()

    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.answer("Профиль сохранён!")
    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ Профиль *{designer.d7_nick}* успешно сохранён!\n\n"
        "Теперь вы можете сдавать отчёты: /report",
        parse_mode="Markdown",
    )
    logger.info("Designer registered/updated: %s (tg_id=%s)", designer.d7_nick, user.id)


@router.callback_query(RegisterStates.confirm, F.data == "reg_confirm:no")
async def cb_confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "✏️ Регистрация отменена. Начните заново: /register"
    )
