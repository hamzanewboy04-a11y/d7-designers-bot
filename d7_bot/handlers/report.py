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
from d7_bot.db import Database, ReviewerEntry, TaskEntry, moscow_today
from d7_bot.handlers.reviewer_v2 import ReviewerV2States
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
    reviewer_geo = State()
    reviewer_count = State()
    reviewer_unit_price = State()
    reviewer_confirm = State()


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

    yesterday = (moscow_today() - timedelta(days=1)).isoformat()

    if designer.role == "reviewer":
        await state.clear()
        await state.set_state(ReviewerV2States.choose_date)
        await state.update_data(items=[])
        await message.answer(
            "🧾 <b>Отчёт отзовика v2</b>\n\n"
            "Это основной сценарий для отзовиков.\n"
            f"Отправь дату отчёта в формате <code>YYYY-MM-DD</code>.\n"
            f"Обычно это вчера: <code>{yesterday}</code>\n\n"
            "Если нужен старый flow: <code>/report_reviews_legacy</code>"
        )
        return

    await state.set_state(ReportStates.choose_date)
    await message.answer(
        "📝 <b>Сдать отчёт по задачам</b>\n\n"
        "Обычно отчёт сдают <b>за вчера</b>. Сначала выберите дату, за которую хотите отправить задачи.\n\n"
        f"📅 Вчера: <b>{yesterday}</b>\n\n"
        "После выбора даты бот попросит вас отправить задачи строками в формате:\n"
        "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>",
        reply_markup=date_keyboard(),
    )


# ── Date selection callbacks ───────────────────────────────────────────────

_TASK_FORMAT_HINT = (
    "<b>Как отправить задачи:</b>\n"
    "Введите каждую задачу с новой строки в формате:\n"
    "<code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n\n"
    "Каждая задача — с новой строки. Допустимые префиксы:\n"
    f"<code>{_ALLOWED_PREFIXES_DISPLAY}</code>\n\n"
    "Примеры:\n"
    "<code>OTHER-1234 12.50\n"
    "PERU1-5678 8.00\n"
    "V-1001 5.00</code>\n\n"
    "<b>Что будет дальше:</b>\n"
    "Бот проверит формат, пропустит дубликаты и покажет, что именно принято.\n\n"
    "<i>/cancel — отменить</i>"
)


@router.callback_query(ReportStates.choose_date, F.data == "report_date:yesterday")
async def cb_date_yesterday(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    yesterday = (moscow_today() - timedelta(days=1)).isoformat()
    await state.update_data(report_date=yesterday)
    await callback.answer()
    designer = await db.get_designer(callback.from_user.id) if callback.from_user else None
    if designer and designer.role == "reviewer":
        await state.set_state(ReportStates.reviewer_geo)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"📝 <b>Отчёт по отзывам за вчера ({yesterday})</b>\n\nУкажи гео отзывов. Например: US, UK, DE, FR."
        )
        return
    await state.set_state(ReportStates.tasks)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Отчёт за вчера ({yesterday})</b>\n\n" + _TASK_FORMAT_HINT
    )


@router.callback_query(ReportStates.choose_date, F.data == "report_date:today")
async def cb_date_today(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    today = moscow_today().isoformat()
    await state.update_data(report_date=today)
    await callback.answer()
    designer = await db.get_designer(callback.from_user.id) if callback.from_user else None
    if designer and designer.role == "reviewer":
        await state.set_state(ReportStates.reviewer_geo)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"📝 <b>Отчёт по отзывам за сегодня ({today})</b>\n\nУкажи гео отзывов. Например: US, UK, DE, FR."
        )
        return
    await state.set_state(ReportStates.tasks)
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
async def step_custom_date(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        await message.answer(
            "❌ <b>Неверный формат даты.</b>\n\n"
            "Используйте формат: <code>YYYY-MM-DD</code>\n"
            "Пример: <code>2024-01-15</code>\n\n"
            "Попробуйте ещё раз или /cancel для отмены."
        )
        return

    report_date = parsed.isoformat()
    await state.update_data(report_date=report_date)
    designer = await db.get_designer(message.from_user.id) if message.from_user else None
    if designer and designer.role == "reviewer":
        await state.set_state(ReportStates.reviewer_geo)
        await message.answer(
            f"📝 <b>Отчёт по отзывам за {report_date}</b>\n\nУкажи гео отзывов. Например: US, UK, DE, FR."
        )
        return
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
            "⚠️ Пустой ввод.\n\nОтправьте хотя бы одну задачу строкой вида <code>OTHER-1234 12.50</code> или используйте /cancel."
        )
        return

    state_data = await state.get_data()
    report_date = state_data.get("report_date", moscow_today().isoformat())

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
            "Проверьте формат: <code>КОД_ЗАДАЧИ СТОИМОСТЬ_USDT</code>\n"
            "Пример: <code>OTHER-1234 12.50</code>"
        )
        return

    await state.clear()
    await message.answer(
        "\n\n".join(parts_resp)
        + "\n\n<b>Что дальше:</b>\n"
        "• если задачи приняты, они уже попали в систему\n"
        "• если были дубликаты или ошибки, можно исправить только проблемные строки и отправить заново\n"
        "• посмотреть себя можно через <b>📋 Мои задачи</b> и <b>👤 Мой профиль</b>",
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


@router.message(Command("report_reviews_legacy"))
async def cmd_report_reviews_legacy(message: Message, state: FSMContext, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer or designer.role != "reviewer":
        await message.answer("⛔ Legacy reviewer flow доступен только отзовикам.")
        return

    yesterday = (moscow_today() - timedelta(days=1)).isoformat()
    await state.clear()
    await state.set_state(ReportStates.choose_date)
    await message.answer(
        "📝 <b>Legacy reviewer flow</b>\n\n"
        "Обычно вы сдаёте отчёт за вчера — выберите нужную дату:\n\n"
        f"📅 Вчера: <b>{yesterday}</b>",
        reply_markup=date_keyboard(),
    )


@router.message(ReportStates.reviewer_geo)
async def reviewer_geo_step(message: Message, state: FSMContext) -> None:
    geo = (message.text or '').strip().upper()
    if not geo:
        await message.answer('⚠️ Укажи гео отзывов. Например: US, UK, DE.')
        return
    await state.update_data(review_geo=geo)
    await state.set_state(ReportStates.reviewer_count)
    await message.answer('Сколько отзывов было сделано?')


@router.message(ReportStates.reviewer_count)
async def reviewer_count_step(message: Message, state: FSMContext) -> None:
    raw = (message.text or '').strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer('⚠️ Введи количество отзывов целым положительным числом.')
        return
    await state.update_data(review_count=int(raw))
    await state.set_state(ReportStates.reviewer_unit_price)
    await message.answer('Какая цена за 1 отзыв в USDT?')


@router.message(ReportStates.reviewer_unit_price)
async def reviewer_unit_price_step(message: Message, state: FSMContext) -> None:
    raw = (message.text or '').strip().replace(',', '.')
    try:
        unit_price = float(raw)
        if unit_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer('⚠️ Введи цену за 1 отзыв положительным числом. Например: 0.5 или 1.25')
        return

    data = await state.get_data()
    report_date = data.get('report_date')
    review_geo = data.get('review_geo')
    review_count = int(data.get('review_count') or 0)
    total = review_count * unit_price

    await state.update_data(unit_price=unit_price, total_cost=total)
    await state.set_state(ReportStates.reviewer_confirm)
    await message.answer(
        'Проверь отчёт:\n\n'
        f'Дата: {report_date}\n'
        f'Гео: {review_geo}\n'
        f'Количество отзывов: {review_count}\n'
        f'Цена за 1 отзыв: {unit_price:.2f} USDT\n'
        f'Итого: {total:.2f} USDT\n\n'
        'Отправь <code>да</code>, чтобы сохранить, или <code>/cancel</code>, чтобы отменить.'
    )


@router.message(ReportStates.reviewer_confirm)
async def reviewer_confirm_step(
    message: Message,
    state: FSMContext,
    db: Database,
    sheets: GoogleSheetsExporter,
    bot: Bot,
    config: Config,
) -> None:
    text = (message.text or '').strip().lower()
    if text in {'нет', 'no', 'n'}:
        await state.clear()
        await message.answer('Ок, отчёт не сохранён.', reply_markup=main_menu_keyboard())
        return
    if text not in {'да', 'yes', 'y'}:
        await message.answer('Отправь <code>да</code>, чтобы сохранить отчёт, или <code>/cancel</code>, чтобы отменить.')
        return

    user = message.from_user
    if not user:
        return
    designer = await db.get_designer(user.id)
    if not designer:
        await state.clear()
        await message.answer('❌ Профиль не найден. Пройдите регистрацию заново.')
        return

    data = await state.get_data()
    entry = ReviewerEntry(
        subject_user_id=designer.telegram_id,
        entered_by_user_id=designer.telegram_id,
        report_date=data['report_date'],
        review_geo=data['review_geo'],
        review_count=int(data['review_count']),
        unit_price=float(data['unit_price']),
        comment=(data.get('comment') or ''),
    )
    added = await db.add_reviewer_entry(entry)
    if not added:
        await state.clear()
        await message.answer('⚠️ Такой отчёт уже существует за эту дату. Проверь дубликаты.', reply_markup=main_menu_keyboard())
        return

    await state.clear()
    await message.answer(
        f'✅ Отчёт по отзывам сохранён.\n\nГео: {entry.review_geo}\nКоличество: {entry.review_count}\nЦена за 1 отзыв: {entry.unit_price:.2f} USDT\nИтого: {entry.cost_usdt:.2f} USDT',
        reply_markup=main_menu_keyboard(),
    )

    if sheets.is_enabled:
        try:
            await sheets.append_reviewer_row(
                designer,
                entry.report_date,
                entry.review_geo,
                entry.review_count,
                entry.unit_price,
                entry.cost_usdt,
                entry.comment,
            )
        except Exception as exc:
            logger.error('Sheets export failed for reviewer entry: %s', exc)

    admin_ids = set(config.admin_ids) | set(await db.list_admins())
    notify_text = (
        f"📬 <b>Новый отчёт от {html.escape(designer.d7_nick)}</b>\n"
        f"📅 Дата: {html.escape(entry.report_date)}\n"
        f"💳 Кошелёк: <code>{html.escape(designer.wallet)}</code>\n\n"
        f"📝 <b>Отзовики</b>\n"
        f"• Гео: {html.escape(entry.review_geo)}\n"
        f"• Количество отзывов: {entry.review_count}\n"
        f"• Цена за 1 отзыв: {entry.unit_price:.2f} USDT\n"
        f"💰 Сумма: <b>{entry.cost_usdt:.2f} USDT</b>\n\n"
        f"Отметьте статус оплаты:"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, notify_text, reply_markup=payment_keyboard(user.id, entry.report_date))
        except Exception as exc:
            logger.warning('Could not notify admin %s about reviewer report: %s', admin_id, exc)
