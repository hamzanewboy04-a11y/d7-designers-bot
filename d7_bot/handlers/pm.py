from __future__ import annotations

import html
import logging
from datetime import timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from d7_bot.config import Config
from d7_bot.db import Database, Employee, moscow_today
from d7_bot.keyboards import main_menu_keyboard
from services.reviewer_domain import ReviewerDomainService
from services.smm_domain import SmmDomainService

logger = logging.getLogger(__name__)
router = Router(name="pm")


class PmSmmEntryStates(StatesGroup):
    choose_smm = State()
    choose_назначение = State()
    choose_date = State()
    enter_comment = State()


async def _check_pm(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> Employee | None:
    user = message.from_user
    if not user:
        return None

    identity_backend = reviewer_domain or db
    employee = await identity_backend.get_employee_by_telegram_id(user.id)
    is_admin = await identity_backend.is_admin(user.id, config.admin_ids)
    if not employee:
        if is_admin:
            return None
        await message.answer("⛔ Профиль сотрудника не найден.")
        return None

    if employee.role != "project_manager" and not is_admin:
        await message.answer("⛔ Только проджект-менеджер или администратор может вносить SMM-отчёты.")
        return None
    return employee


@router.message(Command("pm_review_queue"))
async def cmd_pm_review_queue(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    backend = reviewer_domain or db
    rows = await backend.list_pending_review_entries(limit=20)
    if not rows:
        await message.answer("ℹ️ Сейчас нет отчётов отзовиков, ожидающих проверки.")
        return

    lines = ["🧾 <b>Отчёты отзовиков, ожидающие проверки</b>", ""]
    for item in rows:
        lines.append(
            f"• entry <code>{item['review_entry_id']}</code> | <b>{html.escape(item['display_name'])}</b>\n"
            f"  date {html.escape(item['report_date'])} | {item['item_count']} lines | <b>{item['total_usdt']:.2f} USDT</b>"
        )
    lines.append(
        "\nКоманды:\n"
        "<code>/pm_review_verify &lt;entry_id&gt;</code>\n"
        "<code>/pm_review_reject &lt;entry_id&gt; [comment]</code>"
    )
    await message.answer("\n".join(lines))


@router.message(Command("pm_review_verify"))
async def cmd_pm_review_verify(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: <code>/pm_review_verify &lt;entry_id&gt;</code>\n"
            "Пример: <code>/pm_review_verify 5</code>"
        )
        return

    backend = reviewer_domain or db
    result = await backend.verify_review_entry(int(args[1].strip()), pm.id)
    if not result:
        await message.answer("❌ Reviewer entry не найден или уже обработан.")
        return

    await message.answer(
        "✅ <b>Отчёт отзовика подтверждён</b>\n\n"
        f"Entry: <code>{result['review_entry_id']}</code>\n"
        f"Сотрудник: <b>{html.escape(result['display_name'])}</b>\n"
        f"Дата: <b>{html.escape(result['report_date'])}</b>\n"
        f"Строк: <b>{result['item_count']}</b>\n"
        f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату."
    )


@router.message(Command("pm_review_reject"))
async def cmd_pm_review_reject(
    message: Message,
    db: Database,
    config: Config,
    bot: Bot,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    parts = (message.text or '').split(maxsplit=2)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "Использование: <code>/pm_review_reject &lt;entry_id&gt; [comment]</code>\n"
            "Пример: <code>/pm_review_reject 5 price mismatch</code>"
        )
        return

    entry_id = int(parts[1].strip())
    comment = parts[2].strip() if len(parts) > 2 else ''
    backend = reviewer_domain or db
    result = await backend.reject_review_entry(entry_id, pm.id, comment)
    if not result:
        await message.answer("❌ Reviewer entry не найден или уже обработан.")
        return

    await message.answer(
        "🚫 <b>Отчёт отзовика отклонён</b>\n\n"
        f"Entry: <code>{result['review_entry_id']}</code>\n"
        f"Сотрудник: <b>{html.escape(result['display_name'])}</b>\n"
        f"Дата: <b>{html.escape(result['report_date'])}</b>\n"
        f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату."
        + (f"\nКомментарий: <i>{html.escape(comment)}</i>" if comment else "")
    )

    reviewer = await backend.get_employee(result['employee_id'])
    if reviewer and reviewer.telegram_id:
        try:
            await bot.send_message(
                reviewer.telegram_id,
                "🚫 <b>Твой reviewer-отчёт отклонён</b>\n\n"
                f"Entry ID: <code>{result['review_entry_id']}</code>\n"
                f"Дата: <b>{html.escape(result['report_date'])}</b>\n"
                + (f"Комментарий: <i>{html.escape(comment)}</i>\n" if comment else "")
                + "\nИсправь данные и отправь отчёт заново.",
            )
        except Exception as exc:
            logger.warning("Could not notify reviewer %s about reject: %s", reviewer.telegram_id, exc)


@router.message(Command("pm_review_batch_create"))
async def cmd_pm_review_batch_create(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    backend = reviewer_domain or db
    created = await backend.create_reviewer_payout_batches()
    if not created:
        await message.answer("ℹ️ Сейчас нет новых подтверждённых отчётов отзовиков для формирования пачек выплат.")
        return

    total = sum(item['total_usdt'] for item in created)
    lines = ["🧾 <b>Reviewer payout batches created</b>", f"💰 Итого: <b>{total:.2f} USDT</b>", ""]
    for item in created:
        lines.append(
            f"• batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>"
            f" | entry <code>{item['review_entry_id']}</code> | {item['total_usdt']:.2f} USDT"
        )
    lines.append("\nПосмотреть ожидающие пачки выплат: <code>/pm_review_batches</code>")
    await message.answer("\n".join(lines))


@router.message(Command("pm_review_batches"))
async def cmd_pm_review_batches(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    backend = reviewer_domain or db
    rows = await backend.list_pending_reviewer_batches()
    if not rows:
        await message.answer("ℹ️ Сейчас нет reviewer пачек выплат, ожидающих оплату.")
        return

    lines = ["📦 <b>Pending reviewer batches</b>", ""]
    for item in rows:
        lines.append(
            f"• batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>\n"
            f"  {html.escape(item['period_start'])} | {item['item_count']} строк | <b>{item['total_usdt']:.2f} USDT</b>"
        )
    lines.append("\nОплатить: <code>/pm_review_batch_paid &lt;batch_id&gt;</code>")
    await message.answer("\n".join(lines))


@router.message(Command("pm_review_batch_paid"))
async def cmd_pm_review_batch_paid(
    message: Message,
    db: Database,
    config: Config,
    bot: Bot,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: <code>/pm_review_batch_paid &lt;batch_id&gt;</code>\n"
            "Пример: <code>/pm_review_batch_paid 11</code>"
        )
        return

    backend = reviewer_domain or db
    result = await backend.mark_reviewer_batch_paid(int(args[1].strip()), pm.id)
    if not result:
        await message.answer("❌ Pending reviewer batch не найден или уже закрыт.")
        return

    await message.answer(
        "✅ <b>Пачка выплат отзовику отмечена как оплаченная</b>\n\n"
        f"Пачка: <code>{result['batch_id']}</code>\n"
        f"Сотрудник: <b>{html.escape(result['display_name'])}</b>\n"
        f"Дата: <b>{html.escape(result['period_start'])}</b>\n"
        f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату."
    )

    reviewer = await backend.get_employee(result['employee_id'])
    if reviewer and reviewer.telegram_id:
        try:
            await bot.send_message(
                reviewer.telegram_id,
                "💸 <b>Твоя выплата по reviewer-отчёту отправлена</b>\n\n"
                f"Пачка: <code>{result['batch_id']}</code>\n"
                f"Дата: <b>{html.escape(result['period_start'])}</b>\n"
                f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату.",
            )
        except Exception as exc:
            logger.warning("Could not notify reviewer %s about paid batch: %s", reviewer.telegram_id, exc)


@router.message(Command("pm_review_batch_history"))
async def cmd_pm_review_batch_history(
    message: Message,
    db: Database,
    config: Config,
    reviewer_domain: ReviewerDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, reviewer_domain)
    if not pm:
        return

    backend = reviewer_domain or db
    rows = await backend.list_recent_reviewer_batches(limit=15)
    if not rows:
        await message.answer("ℹ️ Reviewer batch history пока пустая.")
        return

    lines = ["🧾 <b>Reviewer batch history</b>", ""]
    for item in rows:
        status_icon = '✅' if item['status'] == 'paid' else '⏳'
        paid_at = f" | оплачено {html.escape(str(item['paid_at']))[:10]}" if item['paid_at'] else ''
        lines.append(
            f"{status_icon} batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>\n"
            f"  {html.escape(item['period_start'])} | {item['item_count']} строк | <b>{item['total_usdt']:.2f} USDT</b>{paid_at}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_assign"))
async def cmd_pm_smm_assign(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    parts = (message.text or "").split(maxsplit=4)
    if len(parts) < 5:
        await message.answer(
            "Использование: <code>/pm_smm_assign &lt;employee_id&gt; &lt;channel_name&gt; &lt;geo&gt; &lt;daily_rate&gt;</code>\n"
            "Пример: <code>/pm_smm_assign 12 PeruNews PERU 15</code>"
        )
        return

    employee_id_raw, channel_name, geo, rate_raw = parts[1], parts[2], parts[3], parts[4]
    if not employee_id_raw.isdigit():
        await message.answer("❌ employee_id должен быть числом.")
        return

    backend = smm_domain or db
    employee = await backend.get_employee(int(employee_id_raw))
    if not employee or employee.role != "smm" or not employee.is_active:
        await message.answer("❌ Активный SMM сотрудник не найден.")
        return

    try:
        daily_rate = float(rate_raw.replace(',', '.'))
        if daily_rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ daily_rate должен быть положительным числом.")
        return

    назначение_id = await backend.add_smm_назначение(
        smm_employee_id=employee.id,
        channel_name=channel_name,
        geo=geo.upper(),
        daily_rate_usdt=daily_rate,
        active_from=moscow_today().isoformat(),
    )
    await message.answer(
        "✅ <b>Назначение для SMM создано</b>\n\n"
        f"Сотрудник: <b>{html.escape(employee.display_name)}</b>\n"
        f"Канал: <b>{html.escape(channel_name)}</b>\n"
        f"Гео: <b>{html.escape(geo.upper())}</b>\n"
        f"Ставка: <b>{daily_rate:.2f} USDT/день</b>\n"
        f"Assignment ID: <code>{назначение_id}</code>"
    )


@router.message(Command("pm_smm_назначениеs"))
async def cmd_pm_smm_назначениеs(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    backend = smm_domain or db
    rows = await backend.list_active_smm_назначениеs_detailed()
    if not rows:
        await message.answer("ℹ️ Сейчас нет активных SMM-назначений.")
        return

    lines = ["📋 <b>Активные SMM назначениеs</b>", ""]
    current_employee_id: int | None = None
    for назначение, employee in rows:
        if employee.id != current_employee_id:
            current_employee_id = employee.id
            lines.append(f"👤 <b>{html.escape(employee.display_name)}</b> — ID сотрудника <code>{employee.id}</code>")
        lines.append(
            f"• назначение ID <code>{назначение.id}</code> | <b>{html.escape(назначение.channel_name)}</b>"
            f" | {html.escape(назначение.geo or '—')} | {назначение.daily_rate_usdt:.2f} USDT/день"
        )

    await message.answer("\n".join(lines))


def _last_week_range() -> tuple[str, str]:
    today = moscow_today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return last_monday.isoformat(), last_sunday.isoformat()


@router.message(Command("pm_smm_weekly"))
async def cmd_pm_smm_weekly(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    period_start, period_end = _last_week_range()
    backend = smm_domain or db
    rows = await backend.get_smm_weekly_summary(period_start, period_end)
    if not rows:
        await message.answer(
            f"ℹ️ За период <code>{period_start}</code> — <code>{period_end}</code> у SMM нет записей."
        )
        return

    grand_total = sum(item['total_usdt'] for item in rows)
    lines = [
        "💸 <b>SMM weekly payroll preview</b>",
        f"📅 Период: <code>{period_start}</code> — <code>{period_end}</code>",
        f"💰 Итого по всем SMM: <b>{grand_total:.2f} USDT</b>",
        "",
    ]
    for item in rows:
        lines.append(
            f"• <b>{html.escape(item['display_name'])}</b> — ID сотрудника <code>{item['employee_id']}</code>\n"
            f"  {item['entry_count']} записей / {item['day_count']} дней / <b>{item['total_usdt']:.2f} USDT</b>"
        )

    lines.append("\nДля детализации: <code>/pm_smm_weekly_employee &lt;employee_id&gt;</code>")
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_weekly_employee"))
async def cmd_pm_smm_weekly_employee(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: <code>/pm_smm_weekly_employee &lt;employee_id&gt;</code>\n"
            "Пример: <code>/pm_smm_weekly_employee 12</code>"
        )
        return

    backend = smm_domain or db
    employee = await backend.get_employee(int(args[1].strip()))
    if not employee or employee.role != 'smm':
        await message.answer("❌ SMM сотрудник не найден.")
        return

    period_start, period_end = _last_week_range()
    rows = await backend.get_smm_weekly_details(employee.id, period_start, period_end)
    if not rows:
        await message.answer(
            f"ℹ️ У <b>{html.escape(employee.display_name)}</b> нет записей за период <code>{period_start}</code> — <code>{period_end}</code>."
        )
        return

    total = sum(item['total_usdt'] for item in rows)
    lines = [
        f"💼 <b>{html.escape(employee.display_name)}</b>",
        f"📅 Период: <code>{period_start}</code> — <code>{period_end}</code>",
        f"💰 Итого: <b>{total:.2f} USDT</b>",
        "",
    ]
    for item in rows:
        comment_part = f" | {html.escape(item['comment'])}" if item['comment'] else ""
        lines.append(
            f"• <code>{html.escape(item['report_date'])}</code> | <b>{html.escape(item['channel_name'])}</b>"
            f" | {html.escape(item['geo'] or '—')} | {item['total_usdt']:.2f} USDT{comment_part}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_batch_create"))
async def cmd_pm_smm_batch_create(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    period_start, period_end = _last_week_range()
    backend = smm_domain or db
    created = await backend.create_smm_weekly_batches(period_start, period_end)
    if not created:
        await message.answer(
            f"ℹ️ За период <code>{period_start}</code> — <code>{period_end}</code> нет новых SMM-записей для формирования пачек выплат."
        )
        return

    grand_total = sum(item['total_usdt'] for item in created)
    lines = [
        "🧾 <b>SMM weekly payout batches created</b>",
        f"📅 Период: <code>{period_start}</code> — <code>{period_end}</code>",
        f"💰 Итого: <b>{grand_total:.2f} USDT</b>",
        "",
    ]
    for item in created:
        lines.append(
            f"• batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>"
            f" — {item['total_usdt']:.2f} USDT"
        )
    lines.append("\nПосмотреть ожидающие пачки выплат: <code>/pm_smm_batches</code>")
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_batches"))
async def cmd_pm_smm_batches(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    backend = smm_domain or db
    rows = await backend.list_pending_smm_batches()
    if not rows:
        await message.answer("ℹ️ Сейчас нет SMM пачек выплат, ожидающих оплату.")
        return

    lines = ["📦 <b>Пачки выплат SMM, ожидающие оплату</b>", ""]
    for item in rows:
        lines.append(
            f"• batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>\n"
            f"  ID сотрудника <code>{item['employee_id']}</code> | {html.escape(item['period_start'])} — {html.escape(item['period_end'])}\n"
            f"  {item['item_count']} строк | <b>{item['total_usdt']:.2f} USDT</b>"
        )
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_batch_paid"))
async def cmd_pm_smm_batch_paid(
    message: Message,
    db: Database,
    config: Config,
    bot: Bot,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: <code>/pm_smm_batch_paid &lt;batch_id&gt;</code>\n"
            "Пример: <code>/pm_smm_batch_paid 17</code>"
        )
        return

    backend = smm_domain or db
    result = await backend.mark_smm_batch_paid(int(args[1].strip()), pm.id)
    if not result:
        await message.answer("❌ Pending SMM batch не найден или уже закрыт.")
        return

    await message.answer(
        "✅ <b>Пачка выплат SMM отмечена как оплаченная</b>\n\n"
        f"Пачка: <code>{result['batch_id']}</code>\n"
        f"Сотрудник: <b>{html.escape(result['display_name'])}</b>\n"
        f"Период: <code>{html.escape(result['period_start'])}</code> — <code>{html.escape(result['period_end'])}</code>\n"
        f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату."
    )

    smm_employee = await backend.get_employee(result['employee_id'])
    if smm_employee and smm_employee.telegram_id:
        try:
            await bot.send_message(
                smm_employee.telegram_id,
                "💸 <b>Твоя SMM недельная выплата отправлена</b>\n\n"
                f"Пачка: <code>{result['batch_id']}</code>\n"
                f"Период: <code>{html.escape(result['period_start'])}</code> — <code>{html.escape(result['period_end'])}</code>\n"
                f"Сумма: <b>{result['total_usdt']:.2f} USDT</b>\n\n"
        "<b>Что дальше:</b>\n"
        "Теперь этот отчёт можно включать в batch на выплату.",
            )
        except Exception as exc:
            logger.warning("Could not notify SMM %s about paid batch: %s", smm_employee.telegram_id, exc)


@router.message(Command("pm_smm_batch_history"))
async def cmd_pm_smm_batch_history(
    message: Message,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    backend = smm_domain or db
    rows = await backend.list_recent_smm_batches(limit=15)
    if not rows:
        await message.answer("ℹ️ История выплат SMM пока пустая.")
        return

    lines = ["🧾 <b>История выплат SMM</b>", ""]
    for item in rows:
        status_icon = '✅' if item['status'] == 'paid' else '⏳'
        paid_at = f" | оплачено {html.escape(str(item['paid_at']))[:10]}" if item['paid_at'] else ''
        lines.append(
            f"{status_icon} batch <code>{item['batch_id']}</code> | <b>{html.escape(item['display_name'])}</b>\n"
            f"  {html.escape(item['period_start'])} — {html.escape(item['period_end'])} | {item['item_count']} строк | <b>{item['total_usdt']:.2f} USDT</b>{paid_at}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("pm_smm_report"))
async def cmd_pm_smm_report(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        return

    backend = smm_domain or db
    smm_employees = await backend.list_employees_by_role("smm")
    if not smm_employees:
        await message.answer("ℹ️ В системе пока нет активных SMM-сотрудников.")
        return

    await state.clear()
    await state.set_state(PmSmmEntryStates.choose_smm)

    lines = [
        "🧾 <b>PM → запись за день для SMM</b>",
        "",
        "Выберите SMM-сотрудника и отправьте его <code>ID</code> из списка.",
        "",
    ]
    for employee in smm_employees:
        tg_ref = f"@{html.escape(employee.username)}" if employee.username else f"tg:{employee.telegram_id or '—'}"
        lines.append(
            f"• <b>{html.escape(employee.display_name)}</b> — ID <code>{employee.id}</code> — {tg_ref}"
        )

    await message.answer("\n".join(lines))


@router.message(PmSmmEntryStates.choose_smm)
async def step_choose_smm(
    message: Message,
    state: FSMContext,
    db: Database,
    smm_domain: SmmDomainService | None = None,
) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("⚠️ Отправь числовой ID сотрудника из списка.")
        return

    backend = smm_domain or db
    smm_employee = await backend.get_employee(int(raw))
    if not smm_employee or smm_employee.role != "smm" or not smm_employee.is_active:
        await message.answer("❌ SMM сотрудник не найден или не активен.")
        return

    назначениеs = await backend.list_active_smm_назначениеs(smm_employee.id)
    if not назначениеs:
        await message.answer(
            "⚠️ У этого SMM пока нет активных назначений.\n"
            "Сначала нужно создать назначение с каналом и ставкой."
        )
        await state.clear()
        return

    await state.update_data(smm_employee_id=smm_employee.id)
    await state.set_state(PmSmmEntryStates.choose_назначение)

    lines = [
        f"✅ SMM: <b>{html.escape(smm_employee.display_name)}</b>",
        "",
        "Теперь отправь <code>ID</code> назначение'а:",
        "",
    ]
    for назначение in назначениеs:
        lines.append(
            f"• ID <code>{назначение.id}</code> — <b>{html.escape(назначение.channel_name)}</b>"
            f" | {html.escape(назначение.geo or '—')} | {назначение.daily_rate_usdt:.2f} USDT/день"
        )
    await message.answer("\n".join(lines))


@router.message(PmSmmEntryStates.choose_назначение)
async def step_choose_назначение(
    message: Message,
    state: FSMContext,
    db: Database,
    smm_domain: SmmDomainService | None = None,
) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()
    smm_employee_id = int(data["smm_employee_id"])

    if not raw.isdigit():
        await message.answer("⚠️ Отправь числовой ID назначение'а.")
        return

    backend = smm_domain or db
    назначениеs = await backend.list_active_smm_назначениеs(smm_employee_id)
    назначение = next((a for a in назначениеs if a.id == int(raw)), None)
    if not назначение:
        await message.answer("❌ Назначение не найдено среди активных для этого SMM.")
        return

    default_date = (moscow_today() - timedelta(days=1)).isoformat()
    await state.update_data(
        назначение_id=назначение.id,
        назначение_channel=назначение.channel_name,
        назначение_geo=назначение.geo,
        назначение_rate=назначение.daily_rate_usdt,
    )
    await state.set_state(PmSmmEntryStates.choose_date)
    await message.answer(
        f"✅ Назначение: <b>{html.escape(назначение.channel_name)}</b> | {назначение.daily_rate_usdt:.2f} USDT/день\n\n"
        f"Теперь отправьте дату в формате <code>YYYY-MM-DD</code>.\n"
        f"Если это отчёт за вчера — можно просто отправить: <code>{default_date}</code>"
    )


@router.message(PmSmmEntryStates.choose_date)
async def step_choose_date(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        from datetime import date
        parsed = date.fromisoformat(raw)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте <code>YYYY-MM-DD</code>. Например: <code>2026-03-29</code>")
        return

    await state.update_data(report_date=parsed.isoformat())
    await state.set_state(PmSmmEntryStates.enter_comment)
    await message.answer(
        "Добавьте комментарий к записи или отправьте <code>-</code>, если комментарий не нужен."
    )


@router.message(PmSmmEntryStates.enter_comment)
async def step_enter_comment(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    smm_domain: SmmDomainService | None = None,
) -> None:
    pm = await _check_pm(message, db, config, smm_domain)
    if not pm:
        await state.clear()
        return

    data = await state.get_data()
    backend = smm_domain or db
    smm_employee = await backend.get_employee(int(data["smm_employee_id"]))
    if not smm_employee:
        await state.clear()
        await message.answer("❌ SMM сотрудник не найден.")
        return

    comment_raw = (message.text or "").strip()
    comment = "" if comment_raw == "-" else comment_raw

    entry_id = await backend.add_smm_daily_entry_v2(
        smm_employee_id=smm_employee.id,
        entered_by_pm_id=pm.id,
        report_date=str(data["report_date"]),
        назначение_id=int(data["назначение_id"]),
        channel_name_snapshot=str(data["назначение_channel"]),
        geo_snapshot=str(data.get("назначение_geo") or ""),
        daily_rate_snapshot=float(data["назначение_rate"]),
        comment=comment,
    )

    await state.clear()
    await message.answer(
        "✅ <b>Запись за день для SMM сохранена</b>\n\n"
        f"Сотрудник: <b>{html.escape(smm_employee.display_name)}</b>\n"
        f"Канал: <b>{html.escape(str(data['назначение_channel']))}</b>\n"
        f"Гео: <b>{html.escape(str(data.get('назначение_geo') or '—'))}</b>\n"
        f"Дата: <b>{html.escape(str(data['report_date']))}</b>\n"
        f"Сумма: <b>{float(data['назначение_rate']):.2f} USDT</b>\n"
        f"Entry ID: <code>{entry_id}</code>",
        reply_markup=main_menu_keyboard(is_admin=await (smm_domain or db).is_admin(message.from_user.id, config.admin_ids) if message.from_user else False),
    )
