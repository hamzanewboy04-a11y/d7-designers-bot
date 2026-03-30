from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from d7_bot.config import Config
from d7_bot.db import Database, ReviewEntryItem, moscow_today
from d7_bot.keyboards import main_menu_keyboard
from services.reviewer_domain import ReviewerDomainService

logger = logging.getLogger(__name__)
router = Router(name="reviewer_v2")


class ReviewerV2States(StatesGroup):
    choose_date = State()
    choose_type = State()
    choose_quantity = State()
    choose_price = State()
    choose_comment = State()
    confirm_more = State()
    final_comment = State()


async def _get_reviewer(message: Message, db: Database, reviewer_domain: ReviewerDomainService | None = None):
    user = message.from_user
    if not user:
        return None
    backend = reviewer_domain or db
    employee = await backend.get_employee_by_telegram_id(user.id)
    if not employee or employee.role != "reviewer" or not employee.is_active:
        await message.answer("⛔ Новый reviewer flow доступен только активным отзовикам.")
        return None
    return employee


@router.message(Command("report_reviews_v2"))
async def cmd_report_reviews_v2(
    message: Message,
    state: FSMContext,
    db: Database,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    reviewer = await _get_reviewer(message, db, reviewer_domain)
    if not reviewer:
        return

    default_date = (moscow_today() - timedelta(days=1)).isoformat()
    await state.clear()
    await state.set_state(ReviewerV2States.choose_date)
    await state.update_data(items=[])
    await message.answer(
        "🧾 <b>Отчёт отзовика v2</b>\n\n"
        "Это основной формат отчёта для отзовиков.\n\n"
        f"Сначала отправьте дату отчёта в формате <code>YYYY-MM-DD</code>.\n"
        f"Обычно это вчера: <code>{default_date}</code>\n\n"
        "После даты бот по шагам попросит:\n"
        "• тип отзыва\n"
        "• количество\n"
        "• цену\n"
        "• комментарий"
    )


@router.message(ReviewerV2States.choose_date)
async def step_choose_date(
    message: Message,
    state: FSMContext,
    db: Database,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    reviewer = await _get_reviewer(message, db, reviewer_domain)
    if not reviewer:
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты.\n\n"
            "Используйте <code>YYYY-MM-DD</code>.\n"
            f"Пример: <code>{(moscow_today() - timedelta(days=1)).isoformat()}</code>"
        )
        return

    backend = reviewer_domain or db
    rules = await backend.list_review_rate_rules()
    lines = [
        f"📅 Дата отчёта: <b>{html.escape(parsed.isoformat())}</b>",
        "",
        "<b>Теперь выберите тип отзыва.</b>",
        "Если не уверены в цене — бот покажет дефолтную ставку на следующем шаге.",
        "",
        "Доступные типы:",
    ]
    for rule in rules:
        lines.append(
            f"• <code>{html.escape(rule['review_type'])}</code> — по умолчанию {rule['default_unit_price']:.2f} USDT"
        )
    await state.update_data(report_date=parsed.isoformat())
    await state.set_state(ReviewerV2States.choose_type)
    await message.answer("\n".join(lines))


@router.message(ReviewerV2States.choose_type)
async def step_choose_type(
    message: Message,
    state: FSMContext,
    db: Database,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    review_type = (message.text or "").strip().lower()
    backend = reviewer_domain or db
    rules = await backend.list_review_rate_rules()
    valid_types = {rule['review_type']: rule for rule in rules}
    if review_type not in valid_types:
        await message.answer("❌ Неизвестный тип. Используйте один из типов из списка выше.")
        return

    await state.update_data(current_review_type=review_type, current_default_price=valid_types[review_type]['default_unit_price'])
    await state.set_state(ReviewerV2States.choose_quantity)
    await message.answer("Сколько отзывов этого типа было сделано? Введите целое положительное число.")


@router.message(ReviewerV2States.choose_quantity)
async def step_choose_quantity(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Введите количество целым положительным числом. Например: <code>12</code>")
        return

    await state.update_data(current_quantity=int(raw))
    data = await state.get_data()
    default_price = float(data.get('current_default_price') or 0)
    await state.set_state(ReviewerV2States.choose_price)
    await message.answer(
        f"Теперь укажите цену за 1 отзыв в USDT.\n"
        f"Для этого типа ставка по умолчанию: <b>{default_price:.2f}</b>\n"
        f"Можно отправить своё значение, если оно отличается."
    )


@router.message(ReviewerV2States.choose_price)
async def step_choose_price(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(',', '.')
    try:
        unit_price = float(raw)
        if unit_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число для цены. Например: <code>0.5</code> или <code>1.25</code>")
        return

    await state.update_data(current_unit_price=unit_price)
    await state.set_state(ReviewerV2States.choose_comment)
    await message.answer("Добавьте комментарий к этой строке или отправьте <code>-</code>, если комментарий не нужен.")


@router.message(ReviewerV2States.choose_comment)
async def step_choose_comment(message: Message, state: FSMContext) -> None:
    comment_raw = (message.text or "").strip()
    comment = "" if comment_raw == "-" else comment_raw
    data = await state.get_data()

    review_type = str(data['current_review_type'])
    quantity = int(data['current_quantity'])
    unit_price = float(data['current_unit_price'])
    total_usdt = quantity * unit_price

    items = list(data.get('items', []))
    items.append({
        'review_type': review_type,
        'quantity': quantity,
        'unit_price': unit_price,
        'total_usdt': total_usdt,
        'comment': comment,
    })
    await state.update_data(items=items)
    await state.set_state(ReviewerV2States.confirm_more)

    await message.answer(
        f"✅ Добавлена строка: <b>{html.escape(review_type)}</b> | {quantity} шт | {unit_price:.2f} USDT | <b>{total_usdt:.2f} USDT</b>\n\n"
        "Если хотите добавить ещё одну строку — ответьте <code>yes</code>.\n"
        "Если отчёт уже готов — ответьте <code>no</code>."
    )


@router.message(ReviewerV2States.confirm_more)
async def step_confirm_more(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().lower()
    if raw in {"yes", "y", "да", "+"}:
        await state.set_state(ReviewerV2States.choose_type)
        await message.answer("Ок, добавим ещё одну строку. Отправьте следующий тип отзыва.")
        return
    if raw in {"no", "n", "нет", "-"}:
        await state.set_state(ReviewerV2States.final_comment)
        await message.answer("Теперь можно добавить финальный комментарий ко всему отчёту или отправить <code>-</code>, если он не нужен.")
        return
    await message.answer("Ответьте <code>yes</code> или <code>no</code>.")


@router.message(ReviewerV2States.final_comment)
async def step_final_comment(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    reviewer = await _get_reviewer(message, db, reviewer_domain)
    if not reviewer:
        await state.clear()
        return

    data = await state.get_data()
    items_raw = data.get('items', [])
    if not items_raw:
        await state.clear()
        await message.answer("❌ В отчёте нет строк. Начните заново и добавьте хотя бы одну строку.")
        return

    final_comment_raw = (message.text or "").strip()
    final_comment = "" if final_comment_raw == "-" else final_comment_raw

    items = [
        ReviewEntryItem(
            review_type=item['review_type'],
            quantity=int(item['quantity']),
            unit_price=float(item['unit_price']),
            total_usdt=float(item['total_usdt']),
            comment=item.get('comment', ''),
        )
        for item in items_raw
    ]
    backend = reviewer_domain or db
    review_entry_id = await backend.create_review_entry_v2(
        employee_id=reviewer.id,
        report_date=str(data['report_date']),
        items=items,
        comment=final_comment,
    )
    summary = await backend.get_review_entry_summary(review_entry_id)
    await state.clear()

    total_usdt = float(summary['total_usdt']) if summary else sum(item.total_usdt for item in items)
    item_count = int(summary['item_count']) if summary else len(items)

    await message.answer(
        "✅ <b>Отчёт отзовика v2 сохранён</b>\n\n"
        f"Дата: <b>{html.escape(str(data['report_date']))}</b>\n"
        f"Строк: <b>{item_count}</b>\n"
        f"Сумма: <b>{total_usdt:.2f} USDT</b>\n"
        f"Entry ID: <code>{review_entry_id}</code>\n\n"
        "<b>Что дальше:</b>\n"
        "• отчёт отправлен на проверку PM\n"
        "• после подтверждения он попадёт в пачка выплат на выплату\n"
        "• если PM отклонит отчёт, понадобится исправление или комментарий",
        reply_markup=main_menu_keyboard(
            is_admin=await (reviewer_domain or db).is_admin(message.from_user.id, config.admin_ids)
            if message.from_user else False
        ),
    )
