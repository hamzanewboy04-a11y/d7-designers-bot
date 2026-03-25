from __future__ import annotations

import html
import logging
import re
from datetime import date, timedelta
from typing import NamedTuple

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from d7_bot.config import Config
from d7_bot.db import Database, TaskEntry
from d7_bot.keyboards import date_keyboard, main_menu_keyboard, payment_keyboard
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="report")

# ── Task code validation ───────────────────────────────────────────────────

# Allowed prefixes and their groups/geos
_GEO_PREFIXES = {"OTHER", "PERU2", "PERU1", "ITALY", "ARG", "CHILE"}
_VISUAL_PREFIXES = {"V"}
_ALL_PREFIXES = _GEO_PREFIXES | _VISUAL_PREFIXES

# Pattern: PREFIX-<digits>
_TASK_CODE_RE = re.compile(r"^([A-Z][A-Z0-9]*)-(\d+)$")

_ALLOWED_PREFIXES_DISPLAY = "OTHER, PERU1, PERU2, ITALY, ARG, CHILE, V"


class ParsedTask(NamedTuple):
    task_code: str
    cost_usdt: float
    task_prefix: str
    task_group: str
    task_geo: str


def parse_task_line(line: str) -> ParsedTask | str:
    """
    Parse a single task input line "TASK_CODE COST".
    Returns ParsedTask on success, or an error string on failure.
    """
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return (
            f"❌ <code>{html.escape(line)}</code> — неверный формат. "
            f"Ожидается: <code>КОД_ЗАДАЧИ СТОИМОСТЬ</code>"
        )

    task_code_raw, cost_str = parts
    task_code = task_code_raw.upper()

    # Validate cost first (so we can give a clear error)
    try:
        cost_usdt = float(cost_str.replace(",", "."))
        if cost_usdt <= 0:
            raise ValueError("non-positive")
    except ValueError:
        return (
            f"❌ <code>{html.escape(line)}</code> — некорректная стоимость. "
            f"Ожидается положительное число."
        )

    # Validate task code format
    m = _TASK_CODE_RE.match(task_code)
    if not m:
        return (
            f"❌ <code>{html.escape(task_code_raw)}</code> {html.escape(cost_str)} — "
            f"неверный формат кода задачи. "
            f"Ожидается: <code>ПРЕФИКС-ЦИФРЫ</code>, например <code>OTHER-1234</code>"
        )

    prefix = m.group(1)

    if prefix not in _ALL_PREFIXES:
        return (
            f"❌ <code>{html.escape(task_code_raw)}</code> {html.escape(cost_str)} — "
            f"неизвестный префикс. "
            f"Допустимо: {_ALLOWED_PREFIXES_DISPLAY}"
        )

    if prefix in _GEO_PREFIXES:
        task_group = "geo"
        task_geo = prefix
    else:
        task_group = "visual"
        task_geo = ""

    return ParsedTask(
        task_code=task_code,
        cost_usdt=cost_usdt,
        task_prefix=prefix,
        task_group=task_group,
        task_geo=task_geo,
    )


# ── FSM states ─────────────────────────────────────────────────────────────


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

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await state.set_state(ReportStates.choose_date)
    await message.answer(
        "📝 <b>Сдать отчёт по задачам</b>\n\n"
        "Обычно вы сдаёте отчёт <b>за вчера</b> — выберите нужную дату:\n\n"
        f"📅 Вчера: <b>{yesterday}</b>",
        reply_markup=date_keyboard(),
    )


# ── Date selection callbacks ───────────────────────────────────────────────

_TASK_FORMAT_HINT = (
    "Введите задачи в формате:\n"
    "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n\n"
    "Каждая задача — с новой строки. Допустимые префиксы:\n"
    f"<code>{_ALLOWED_PREFIXES_DISPLAY}</code>\n\n"
    "Примеры:\n"
    "<code>OTHER-1234 12.50\n"
    "PERU1-5678 8.00\n"
    "V-1001 5.00</code>\n\n"
    "<i>/cancel — отменить</i>"
)


@router.callback_query(ReportStates.choose_date, F.data == "report_date:yesterday")
async def cb_date_yesterday(callback: CallbackQuery, state: FSMContext) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await state.update_data(report_date=yesterday)
    await state.set_state(ReportStates.tasks)
    await callback.answer()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Отчёт за вчера ({yesterday})</b>\n\n" + _TASK_FORMAT_HINT
    )


@router.callback_query(ReportStates.choose_date, F.data == "report_date:today")
async def cb_date_today(callback: CallbackQuery, state: FSMContext) -> None:
    today = date.today().isoformat()
    await state.update_data(report_date=today)
    await state.set_state(ReportStates.tasks)
    await callback.answer()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Отчёт за сегодня ({today})</b>\n\n" + _TASK_FORMAT_HINT
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
        f"📝 <b>Отчёт за {report_date}</b>\n\n" + _TASK_FORMAT_HINT
    )


# ── Task input ─────────────────────────────────────────────────────────────


@router.message(ReportStates.tasks)
async def step_tasks(
    message: Message,
    state: FSMContext,
    db: Database,
    sheets: GoogleSheetsExporter,
    bot: Bot,
    config: Config,
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

    accepted: list[ParsedTask] = []
    duplicates: list[str] = []
    errors: list[str] = []

    for line in lines:
        result = parse_task_line(line)
        if isinstance(result, str):
            # It's an error message
            errors.append(result)
            continue

        parsed = result
        task = TaskEntry(
            designer_id=user.id,
            report_date=report_date,
            task_code=parsed.task_code,
            cost_usdt=parsed.cost_usdt,
            task_prefix=parsed.task_prefix,
            task_group=parsed.task_group,
            task_geo=parsed.task_geo,
        )
        added = await db.add_task(task)
        if added:
            accepted.append(parsed)
        else:
            duplicates.append(
                f"• <code>{html.escape(parsed.task_code)}</code> — уже сдана за {html.escape(report_date)}"
            )

    # Build response
    parts_resp: list[str] = []

    if accepted:
        total_accepted = sum(p.cost_usdt for p in accepted)
        parts_resp.append(
            f"✅ <b>Принято задач: {len(accepted)}</b>\n"
            f"💰 Сумма: {total_accepted:.2f} USDT\n"
            f"📅 Дата: {report_date}"
        )
    if duplicates:
        parts_resp.append("⚠️ <b>Дубликаты (пропущены):</b>\n" + "\n".join(duplicates))
    if errors:
        parts_resp.append(
            "❌ <b>Ошибки:</b>\n"
            + "\n".join(errors)
            + f"\n\n<i>Допустимые префиксы: {_ALLOWED_PREFIXES_DISPLAY}</i>"
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

    # Notify admins about the new report with payment buttons
    if accepted:
        total_accepted = sum(p.cost_usdt for p in accepted)
        nick_safe = html.escape(designer.d7_nick)
        wallet_safe = html.escape(designer.wallet)
        date_safe = html.escape(report_date)
        task_lines = "\n".join(
            f"• {html.escape(pt.task_code)} — {pt.cost_usdt:.2f} USDT"
            for pt in accepted
        )
        notify_text = (
            f"📬 <b>Новый отчёт от {nick_safe}</b>\n"
            f"📅 Дата: {date_safe}\n"
            f"💳 Кошелёк: <code>{wallet_safe}</code>\n\n"
            f"📋 <b>Задачи:</b>\n{task_lines}\n\n"
            f"📦 Всего задач: {len(accepted)}\n"
            f"💰 Сумма: <b>{total_accepted:.2f} USDT</b>\n\n"
            f"Отметьте статус оплаты:"
        )
        admin_ids = set(config.admin_ids) | set(await db.list_admins())
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    notify_text,
                    reply_markup=payment_keyboard(user.id, report_date),
                )
            except Exception as exc:
                logger.warning("Could not notify admin %s: %s", admin_id, exc)

    logger.info(
        "Report from %s (%s) for %s: %d accepted, %d duplicates, %d errors",
        designer.d7_nick,
        user.id,
        report_date,
        len(accepted),
        len(duplicates),
        len(errors),
    )
