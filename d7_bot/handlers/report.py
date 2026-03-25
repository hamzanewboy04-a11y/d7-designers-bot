from __future__ import annotations

import logging
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from d7_bot.db import Database, TaskEntry
from d7_bot.keyboards import date_keyboard, main_menu_keyboard
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="report")


class ReportStates(StatesGroup):
    choose_date = State()
    custom_date = State()
    tasks = State()


# ── /report entry point ────────────────────────────────────────────────────


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ <b>Вы не зарегистрированы.</b>\n\n"
            "Пройдите регистрацию сначала 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(ReportStates.choose_date)
    await message.answer(
        "📝 <b>Сдать отчёт по задачам</b>\n\n"
        "Выберите дату отчёта:",
        reply_markup=date_keyboard(),
    )


# ── Date selection callbacks ───────────────────────────────────────────────


@router.callback_query(ReportStates.choose_date, F.data == "report_date:today")
async def cb_date_today(callback: CallbackQuery, state: FSMContext) -> None:
    today = date.today().isoformat()
    await state.update_data(report_date=today)
    await state.set_state(ReportStates.tasks)
    await callback.answer()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Отчёт за сегодня ({today})</b>\n\n"
        "Введите задачи в формате:\n"
        "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n\n"
        "Каждая задача — с новой строки. Пример:\n"
        "<code>D7-101 12.50\n"
        "D7-102 8.00</code>\n\n"
        "<i>/cancel — отменить</i>"
    )


@router.callback_query(ReportStates.choose_date, F.data == "report_date:yesterday")
async def cb_date_yesterday(callback: CallbackQuery, state: FSMContext) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await state.update_data(report_date=yesterday)
    await state.set_state(ReportStates.tasks)
    await callback.answer()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Отчёт за вчера ({yesterday})</b>\n\n"
        "Введите задачи в формате:\n"
        "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n\n"
        "Каждая задача — с новой строки. Пример:\n"
        "<code>D7-101 12.50\n"
        "D7-102 8.00</code>\n\n"
        "<i>/cancel — отменить</i>"
    )


@router.callback_query(ReportStates.choose_date, F.data == "report_date:custom")
async def cb_date_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReportStates.custom_date)
    await callback.answer()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "📆 <b>Введите дату вручную</b>\n\n"
        "Формат: <code>YYYY-MM-DD</code>\n"
        "Пример: <code>2024-01-15</code>\n\n"
        "<i>/cancel — отменить</i>"
    )


@router.message(ReportStates.custom_date)
async def step_custom_date(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        await message.answer(
            "❌ <b>Неверный формат даты.</b>\n\n"
            "Используйте формат: <code>YYYY-MM-DD</code>\n"
            "Пример: <code>2024-01-15</code>\n\n"
            "Попробуйте ещё раз или /cancel для отмены:"
        )
        return

    report_date = parsed.isoformat()
    await state.update_data(report_date=report_date)
    await state.set_state(ReportStates.tasks)
    await message.answer(
        f"📝 <b>Отчёт за {report_date}</b>\n\n"
        "Введите задачи в формате:\n"
        "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n\n"
        "Каждая задача — с новой строки. Пример:\n"
        "<code>D7-101 12.50\n"
        "D7-102 8.00</code>\n\n"
        "<i>/cancel — отменить</i>"
    )


# ── Task input ─────────────────────────────────────────────────────────────


@router.message(ReportStates.tasks)
async def step_tasks(
    message: Message,
    state: FSMContext,
    db: Database,
    sheets: GoogleSheetsExporter,
) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await state.clear()
        await message.answer(
            "❌ Профиль не найден. Пройдите регистрацию: /register",
            reply_markup=main_menu_keyboard(),
        )
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "⚠️ Пустой ввод. Введите задачи или /cancel для отмены."
        )
        return

    state_data = await state.get_data()
    report_date = state_data.get("report_date", date.today().isoformat())

    lines = [line.strip() for line in raw.splitlines() if line.strip()]

    accepted: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []

    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            errors.append(f"• <code>{line}</code> — неверный формат")
            continue
        task_code, cost_str = parts
        try:
            cost_usdt = float(cost_str.replace(",", "."))
            if cost_usdt <= 0:
                raise ValueError("non-positive")
        except ValueError:
            errors.append(f"• <code>{line}</code> — некорректная стоимость")
            continue

        task = TaskEntry(
            designer_id=user.id,
            report_date=report_date,
            task_code=task_code,
            cost_usdt=cost_usdt,
        )
        added = await db.add_task(task)
        if added:
            accepted.append(line)
        else:
            duplicates.append(f"• <code>{task_code}</code> — уже сдана за {report_date}")

    # Build response
    parts_resp: list[str] = []

    if accepted:
        total_accepted = sum(
            float(ln.split(maxsplit=1)[1].replace(",", "."))
            for ln in accepted
        )
        parts_resp.append(
            f"✅ <b>Принято задач: {len(accepted)}</b>\n"
            f"💰 Сумма: {total_accepted:.2f} USDT\n"
            f"📅 Дата: {report_date}"
        )
    if duplicates:
        parts_resp.append("⚠️ <b>Дубликаты (пропущены):</b>\n" + "\n".join(duplicates))
    if errors:
        parts_resp.append(
            "❌ <b>Ошибки формата:</b>\n"
            + "\n".join(errors)
            + "\n\n<i>Формат: КОД_ЗАДАЧИ СТОИМОСТЬ</i>"
        )

    if not accepted and not duplicates and not errors:
        await message.answer(
            "❌ Не удалось разобрать ни одной задачи.\n\n"
            "Проверьте формат: <code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>"
        )
        return

    await state.clear()
    await message.answer(
        "\n\n".join(parts_resp),
        reply_markup=main_menu_keyboard(),
    )

    # Export accepted lines to Google Sheets
    if accepted and sheets.is_enabled:
        try:
            await sheets.append_report_rows(designer, report_date, accepted)
            logger.info("Sheets: appended %d rows for %s", len(accepted), designer.d7_nick)
        except Exception as exc:
            logger.error("Sheets export failed: %s", exc)

    logger.info(
        "Report from %s (%s) for %s: %d accepted, %d duplicates, %d errors",
        designer.d7_nick,
        user.id,
        report_date,
        len(accepted),
        len(duplicates),
        len(errors),
    )
