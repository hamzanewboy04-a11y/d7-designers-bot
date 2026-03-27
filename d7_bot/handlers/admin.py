from __future__ import annotations

import html
import logging
from datetime import date, datetime, timedelta, timezone

import zoneinfo

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from d7_bot.config import Config
from d7_bot.db import Database
from d7_bot.keyboards import (
    ROLE_LABELS,
    admin_analytics_keyboard,
    admin_employees_keyboard,
    admin_hub_keyboard,
    admin_payments_keyboard,
    admin_reports_keyboard,
    back_to_hub_keyboard,
    payment_keyboard,
)
from d7_bot.sheets import GoogleSheetsExporter
from d7_bot.db import moscow_today

logger = logging.getLogger(__name__)
router = Router(name="admin")

_MOSCOW = zoneinfo.ZoneInfo("Europe/Moscow")


class PaymentCommentStates(StatesGroup):
    waiting_comment = State()


async def _check_admin(message: Message, db: Database, config: Config) -> bool:
    """Reply with error and return False if user is not admin."""
    user = message.from_user
    if not user:
        return False
    if not await db.is_admin(user.id, config.admin_ids):
        await message.answer("⛔ Недостаточно прав.")
        return False
    return True


async def _check_admin_cb(callback: CallbackQuery, db: Database, config: Config) -> bool:
    """Return False (with alert) if callback user is not admin."""
    user = callback.from_user
    if not user:
        return False
    if not await db.is_admin(user.id, config.admin_ids):
        await callback.answer("⛔ Недостаточно прав.", show_alert=True)
        return False
    return True


# ── /addadmin ──────────────────────────────────────────────────────────────


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /addadmin &lt;telegram_id&gt;\n"
            "Пример: <code>/addadmin 123456789</code>",
        )
        return

    new_admin_id = int(args[1].strip())
    current_admins = await db.list_admins()

    if new_admin_id in current_admins or new_admin_id in config.admin_ids:
        await message.answer(
            f"ℹ️ Пользователь <code>{new_admin_id}</code> уже является администратором."
        )
        return

    await db.add_admin(new_admin_id)
    logger.info("Admin added: %s (by %s)", new_admin_id, message.from_user.id)  # type: ignore[union-attr]
    await message.answer(
        f"✅ Пользователь <code>{new_admin_id}</code> добавлен как администратор."
    )


# ── /listdesigners ─────────────────────────────────────────────────────────

# Valid role identifiers
_VALID_ROLES = {"designer", "smm", "reviewer", "project_manager"}


@router.message(Command("listdesigners"))
async def cmd_listdesigners(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    role_filter: str | None = None
    if len(args) >= 2:
        raw_role = args[1].strip().lower()
        if raw_role in _VALID_ROLES:
            role_filter = raw_role
        else:
            await message.answer(
                f"❌ Неизвестная роль: <code>{html.escape(raw_role)}</code>\n\n"
                "Доступные: <code>designer</code>, <code>smm</code>, <code>reviewer</code>, <code>project_manager</code>"
            )
            return

    designers = await db.list_designers_by_role(role_filter)

    if role_filter:
        role_label = ROLE_LABELS.get(role_filter, role_filter)
        header = f"👥 <b>Сотрудники — {html.escape(role_label)} ({len(designers)}):</b>\n"
    else:
        header = f"👥 <b>Список сотрудников ({len(designers)}):</b>\n"

    if not designers:
        await message.answer(header + "\nНикого не найдено.")
        return

    entries: list[str] = []
    for d in designers:
        role_label = ROLE_LABELS.get(d.role, d.role) if d.role else "—"
        role_str = html.escape(role_label)
        nick_safe = html.escape(d.d7_nick)
        wallet_safe = html.escape(d.wallet)
        if d.username:
            tg_link = f"@{html.escape(d.username)}"
        else:
            tg_link = f"id{d.telegram_id}"
        entries.append(
            f"• <b>{nick_safe}</b> ({tg_link})\n"
            f"  Роль: {role_str}\n"
            f"  Кошелёк: <code>{wallet_safe}</code>"
        )

    # Split into chunks to avoid Telegram message size limit
    current_chunks: list[str] = [header]
    current_len = len(header)

    for entry in entries:
        entry_with_sep = "\n" + entry
        if current_len + len(entry_with_sep) > 3800:
            await message.answer("".join(current_chunks))
            current_chunks = []
            current_len = 0
        current_chunks.append(entry_with_sep)
        current_len += len(entry_with_sep)

    if current_chunks:
        await message.answer("".join(current_chunks))


# ── /adminreport ───────────────────────────────────────────────────────────


@router.message(Command("adminreport"))
async def cmd_adminreport(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        report_date = moscow_today() - timedelta(days=1)
    else:
        date_str = args[1].strip()
        try:
            report_date = date.fromisoformat(date_str)
        except ValueError:
            await message.answer(
                "❌ Неверный формат даты. Используйте YYYY-MM-DD.\n"
                "Пример: <code>/adminreport 2024-01-15</code>",
            )
            return

    rows = await db.list_tasks_by_date(report_date)
    date_str_safe = html.escape(report_date.isoformat())

    if not rows:
        await message.answer(f"За <b>{date_str_safe}</b> задач не найдено.")
        return

    lines: list[str] = [f"📊 <b>Отчёт за {date_str_safe}</b>\n"]
    current_nick: str | None = None
    day_total = 0.0
    total = 0.0
    current_payment: str = "pending"

    for d7_nick, wallet, task_code, cost_usdt, payment_status in rows:
        nick_safe = html.escape(str(d7_nick))
        wallet_safe = html.escape(str(wallet))
        code_safe = html.escape(str(task_code))

        if d7_nick != current_nick:
            if current_nick is not None:
                pay_icon = _payment_icon(current_payment)
                lines.append(
                    f"  <i>Итого: {day_total:.2f} USDT {pay_icon}</i>"
                )
            current_nick = d7_nick
            current_payment = payment_status or "pending"
            day_total = 0.0
            lines.append(f"\n👤 <b>{nick_safe}</b> (<code>{wallet_safe}</code>)")
        else:
            # track most "unresolved" status
            if payment_status == "pending":
                current_payment = "pending"
            elif payment_status == "unpaid" and current_payment != "pending":
                current_payment = "unpaid"

        lines.append(f"  • <code>{code_safe}</code> — {cost_usdt:.2f} USDT")
        day_total += cost_usdt
        total += cost_usdt

    if current_nick is not None:
        pay_icon = _payment_icon(current_payment)
        lines.append(f"  <i>Итого: {day_total:.2f} USDT {pay_icon}</i>")

    lines.append(f"\n💰 <b>Итого за день: {total:.2f} USDT</b>")

    # Send in chunks if needed
    text = "\n".join(lines)
    if len(text) <= 4000:
        await message.answer(text)
    else:
        for chunk in _split_text(text, 4000):
            await message.answer(chunk)


# ── /missedreports ─────────────────────────────────────────────────────────


async def _get_missed_text(db: Database, report_date: date) -> str:
    """Build a text summary of who missed their report for report_date."""
    missing = await db.list_missing_reports(report_date)
    date_safe = html.escape(report_date.isoformat())
    if not missing:
        return f"✅ <b>Все сотрудники сдали отчёт за {date_safe}.</b>"

    lines: list[str] = [
        f"⏰ <b>Не сдали отчёт за {date_safe} ({len(missing)} чел.):</b>\n"
    ]
    for d in missing:
        role_label = ROLE_LABELS.get(d.role, d.role) if d.role else "—"
        nick_safe = html.escape(d.d7_nick)
        role_safe = html.escape(role_label)
        tg_ref = f"@{html.escape(d.username)}" if d.username else f"id{d.telegram_id}"
        lines.append(f"• <b>{nick_safe}</b> ({tg_ref}) — {role_safe}")

    return "\n".join(lines)


@router.message(Command("missedreports"))
async def cmd_missedreports(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    yesterday = date.today() - timedelta(days=1)
    text = await _get_missed_text(db, yesterday)
    await message.answer(text)


# ── /employeehistory ───────────────────────────────────────────────────────


@router.message(Command("employeehistory"))
async def cmd_employeehistory(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /employeehistory &lt;telegram_id&gt;\n"
            "Пример: <code>/employeehistory 123456789</code>"
        )
        return

    target_id = int(args[1].strip())
    designer = await db.get_designer(target_id)
    if not designer:
        await message.answer(f"❌ Сотрудник с ID <code>{target_id}</code> не найден.")
        return

    history = await db.get_employee_payment_history(target_id)
    role_label = ROLE_LABELS.get(designer.role, designer.role) if designer.role else "—"
    nick_safe = html.escape(designer.d7_nick)
    role_safe = html.escape(role_label)
    wallet_safe = html.escape(designer.wallet)

    lines: list[str] = [
        f"👤 <b>{nick_safe}</b>",
        f"  Роль: {role_safe}",
        f"  Кошелёк: <code>{wallet_safe}</code>\n",
        f"📊 <b>Статистика выплат:</b>",
        f"  ✅ Оплачено записей: <b>{history['paid_count']}</b>",
        f"  💰 Оплачено сумма: <b>{history['paid_sum']:.2f} USDT</b>",
        f"  ⏳ Ожидают оплаты: <b>{history['pending_count']}</b>",
        f"  ❌ Не оплачено: <b>{history['unpaid_count']}</b>",
    ]

    recent = history["recent"]
    if recent:
        lines.append("\n📋 <b>Последние 10 записей (оплачены/неоплачены):</b>")
        for report_date, task_code, cost_usdt, payment_status, paid_at in recent:
            status_icon = "✅" if payment_status == "paid" else "❌"
            paid_at_str = f" ({html.escape(str(paid_at)[:10])})" if paid_at else ""
            lines.append(
                f"  {status_icon} <code>{html.escape(str(task_code))}</code> "
                f"— {cost_usdt:.2f} USDT "
                f"| {html.escape(str(report_date))}{paid_at_str}"
            )
    else:
        lines.append("\nЗаписей об оплате пока нет.")

    await message.answer("\n".join(lines))


# ── /paidtoday ─────────────────────────────────────────────────────────────


@router.message(Command("paidtoday"))
async def cmd_paidtoday(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return
    await _send_paid_summary(message, db, days=1, label="сегодня")


# ── /paidweek ──────────────────────────────────────────────────────────────


@router.message(Command("paidweek"))
async def cmd_paidweek(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return
    await _send_paid_summary(message, db, days=7, label="за 7 дней")


async def _send_paid_summary(
    message: Message, db: Database, days: int, label: str
) -> None:
    """Send a paid summary for the last `days` days (Moscow date)."""
    today_msk = datetime.now(tz=_MOSCOW).date()
    since_date = today_msk - timedelta(days=days - 1)

    rows = await db.get_paid_summary(since_date)
    if not rows:
        await message.answer(f"💸 Нет оплаченных отчётов {html.escape(label)}.")
        return

    total_sum = sum(float(r[4]) for r in rows)
    total_entries = sum(int(r[3]) for r in rows)
    lines: list[str] = [
        f"✅ <b>Выплачено {html.escape(label)}:</b> "
        f"{total_entries} записей / <b>{total_sum:.2f} USDT</b>\n"
    ]

    # Group by designer
    from collections import defaultdict
    by_nick: dict[str, dict] = defaultdict(lambda: {"entries": 0, "sum": 0.0, "dates": []})
    for _, d7_nick, report_date, task_count, total_usdt in rows:
        by_nick[d7_nick]["entries"] += task_count
        by_nick[d7_nick]["sum"] += total_usdt
        by_nick[d7_nick]["dates"].append(report_date)

    for nick, info in sorted(by_nick.items()):
        nick_safe = html.escape(nick)
        dates_str = ", ".join(sorted(info["dates"]))
        lines.append(
            f"👤 <b>{nick_safe}</b> — {info['entries']} зад. / {info['sum']:.2f} USDT\n"
            f"   📅 {html.escape(dates_str)}"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        for chunk in _split_text(text, 4000):
            await message.answer(chunk)
    else:
        await message.answer(text)


# ── /pendingpayments ───────────────────────────────────────────────────────


@router.message(Command("pendingpayments"))
async def cmd_pendingpayments(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    rows = await db.get_pending_payments()
    if not rows:
        await message.answer("✅ Нет ожидающих оплаты отчётов.")
        return

    await message.answer(
        f"💸 <b>Ожидают оплаты ({len(rows)} записей):</b>\n\n"
        "Нажмите на кнопку под каждым отчётом, чтобы отметить статус оплаты."
    )

    for designer_id, d7_nick, wallet, report_date, task_count, total_usdt in rows:
        nick_safe = html.escape(str(d7_nick))
        wallet_safe = html.escape(str(wallet))
        date_safe = html.escape(str(report_date))
        text = (
            f"👤 <b>{nick_safe}</b>\n"
            f"📅 Дата: {date_safe}\n"
            f"📋 Задач: {task_count}\n"
            f"💰 Сумма: <b>{total_usdt:.2f} USDT</b>\n"
            f"💳 Кошелёк: <code>{wallet_safe}</code>"
        )
        await message.answer(
            text,
            reply_markup=payment_keyboard(designer_id, report_date),
        )


# ── /analyticsday /analyticsweek /analyticsmonth /analyticsfrom ────────────


async def _send_analytics(message: Message, db: Database, start_date: str, end_date: str, label: str) -> None:
    """Build and send analytics message for the given date range."""
    summary = await db.get_analytics_summary(start_date, end_date)
    geo_breakdown = await db.get_geo_breakdown(start_date, end_date)

    label_safe = html.escape(label)
    lines: list[str] = [
        f"📊 <b>Аналитика {label_safe}</b>",
        f"📅 <code>{html.escape(start_date)}</code> — <code>{html.escape(end_date)}</code>\n",
        f"💰 <b>Общая сумма: {summary['total_usdt']:.2f} USDT</b>",
        f"🌍 GEO creatives: <b>{summary['geo_usdt']:.2f} USDT</b>",
        f"🎨 Visuals: <b>{summary['visual_usdt']:.2f} USDT</b>",
        f"📋 Всего задач: {summary['task_count']}",
    ]

    if geo_breakdown:
        lines.append("\n🗺 <b>Разбивка по GEO:</b>")
        for item in geo_breakdown:
            geo_safe = html.escape(item["geo"] or "—")
            lines.append(f"  • {geo_safe}: <b>{item['usdt']:.2f} USDT</b> ({item['count']} зад.)")

    text = "\n".join(lines)
    if len(text) > 4000:
        for chunk in _split_text(text, 4000):
            await message.answer(chunk)
    else:
        await message.answer(text)


@router.message(Command("analyticsday"))
async def cmd_analyticsday(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return
    today = moscow_today().isoformat()
    await _send_analytics(message, db, today, today, "за сегодня")


@router.message(Command("analyticsweek"))
async def cmd_analyticsweek(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return
    end = moscow_today()
    start = end - timedelta(days=6)
    await _send_analytics(message, db, start.isoformat(), end.isoformat(), "за 7 дней")


@router.message(Command("analyticsmonth"))
async def cmd_analyticsmonth(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return
    end = moscow_today()
    start = end - timedelta(days=29)
    await _send_analytics(message, db, start.isoformat(), end.isoformat(), "за 30 дней")


@router.message(Command("analyticsfrom"))
async def cmd_analyticsfrom(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Использование: /analyticsfrom YYYY-MM-DD YYYY-MM-DD\n"
            "Пример: <code>/analyticsfrom 2024-01-01 2024-01-31</code>"
        )
        return

    try:
        start = date.fromisoformat(args[1])
        end = date.fromisoformat(args[2])
    except ValueError:
        await message.answer(
            "❌ Неверный формат дат. Используйте YYYY-MM-DD.\n"
            "Пример: <code>/analyticsfrom 2024-01-01 2024-01-31</code>"
        )
        return

    if start > end:
        await message.answer("❌ Начальная дата не может быть позже конечной.")
        return

    label = f"с {start.isoformat()} по {end.isoformat()}"
    await _send_analytics(message, db, start.isoformat(), end.isoformat(), label)


# ── /dashboard ─────────────────────────────────────────────────────────────


@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    # Gather all data
    today_msk = datetime.now(tz=_MOSCOW).date()
    yesterday = today_msk - timedelta(days=1)
    week_start = today_msk - timedelta(days=6)

    # Designers stats
    role_counts = await db.count_designers_by_role()
    total_employees = role_counts.get("__total__", 0)
    designer_count = role_counts.get("designer", 0)
    smm_count = role_counts.get("smm", 0)
    reviewer_count = role_counts.get("reviewer", 0)
    project_manager_count = role_counts.get("project_manager", 0)

    # Pending payments
    pending = await db.get_pending_payments_summary()

    # Paid today
    paid_today_rows = await db.get_paid_summary(today_msk)
    paid_today_sum = sum(float(r[4]) for r in paid_today_rows)
    paid_today_count = len(paid_today_rows)

    # Paid this week
    paid_week_rows = await db.get_paid_summary(week_start)
    paid_week_sum = sum(float(r[4]) for r in paid_week_rows)
    paid_week_count = len(paid_week_rows)

    # Who missed yesterday
    missing = await db.list_missing_reports(yesterday)
    missed_count = len(missing)

    # Analytics today
    analytics_today = await db.get_analytics_summary(today_msk.isoformat(), today_msk.isoformat())

    # Analytics this week
    analytics_week = await db.get_analytics_summary(week_start.isoformat(), today_msk.isoformat())

    lines: list[str] = [
        "📊 <b>DASHBOARD</b>",
        f"📅 <code>{html.escape(today_msk.isoformat())}</code> (МСК)\n",
        "━━━━━━━━━━━━━━━━━━━━",
        "👥 <b>Сотрудники</b>",
        f"  Всего: <b>{total_employees}</b>",
        f"  🎨 Дизайнеров: {designer_count}",
        f"  📱 SMM: {smm_count}",
        f"  ⭐ Отзовиков: {reviewer_count}",
        f"  🗂 Проджектов: {project_manager_count}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💸 <b>Оплаты</b>",
        f"  ⏳ Ожидают: <b>{pending['count']} записей / {pending['total_usdt']:.2f} USDT</b>",
        f"  ✅ Выплачено сегодня: {paid_today_count} зап. / <b>{paid_today_sum:.2f} USDT</b>",
        f"  📈 Выплачено за 7 дн: {paid_week_count} зап. / <b>{paid_week_sum:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"⏰ <b>Не сдали за вчера ({html.escape(yesterday.isoformat())}):</b> {missed_count} чел.",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📉 <b>Аналитика сегодня</b>",
        f"  💰 {analytics_today['total_usdt']:.2f} USDT ({analytics_today['task_count']} задач)",
        f"  🌍 GEO: {analytics_today['geo_usdt']:.2f} USDT",
        f"  🎨 Visual: {analytics_today['visual_usdt']:.2f} USDT",
        "",
        "📈 <b>Аналитика 7 дней</b>",
        f"  💰 {analytics_week['total_usdt']:.2f} USDT ({analytics_week['task_count']} задач)",
        f"  🌍 GEO: {analytics_week['geo_usdt']:.2f} USDT",
        f"  🎨 Visual: {analytics_week['visual_usdt']:.2f} USDT",
    ]

    await message.answer("\n".join(lines))


# ── Payment callback ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("pay:"))
async def cb_payment(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    config: Config,
    sheets: GoogleSheetsExporter,
    bot: Bot,
) -> None:
    if not await _check_admin_cb(callback, db, config):
        return

    # pay:<status>:<designer_id>:<report_date>
    parts = (callback.data or "").split(":", 3)
    if len(parts) != 4:
        await callback.answer("Ошибка: неверные данные.", show_alert=True)
        return

    _, status, designer_id_str, report_date = parts
    if status not in ("paid", "unpaid"):
        await callback.answer("Неизвестный статус.", show_alert=True)
        return

    try:
        designer_id = int(designer_id_str)
    except ValueError:
        await callback.answer("Ошибка: неверный ID.", show_alert=True)
        return

    admin_id = callback.from_user.id

    if status == "paid":
        # Process payment immediately
        await _process_paid(
            callback=callback,
            db=db,
            sheets=sheets,
            bot=bot,
            designer_id=designer_id,
            report_date=report_date,
            admin_id=admin_id,
        )
    else:
        # status == "unpaid": ask admin for a comment first
        summary = await db.get_report_summary(designer_id, report_date)
        total_usdt = summary.get("total_usdt", 0.0)

        # Save context in FSM
        await state.update_data(
            unpaid_designer_id=designer_id,
            unpaid_report_date=report_date,
            unpaid_total_usdt=total_usdt,
            unpaid_origin_message_id=callback.message.message_id if callback.message else None,
        )
        await state.set_state(PaymentCommentStates.waiting_comment)
        await callback.answer()
        await callback.message.answer(  # type: ignore[union-attr]
            "💬 <b>Укажите причину, почему отчёт не оплачен:</b>\n\n"
            f"Дата: <b>{html.escape(report_date)}</b>\n"
            f"Сумма: <b>{total_usdt:.2f} USDT</b>\n\n"
            "<i>Введите комментарий и нажмите отправить. /cancel — отменить.</i>"
        )


async def _process_paid(
    callback: CallbackQuery,
    db: Database,
    sheets: GoogleSheetsExporter,
    bot: Bot,
    designer_id: int,
    report_date: str,
    admin_id: int,
) -> None:
    """Handle the 'paid' status: update DB, notify designer, update message."""
    await db.update_payment_status(designer_id, report_date, "paid", admin_id)

    # Get summary for notification
    summary = await db.get_report_summary(designer_id, report_date)
    total_usdt = summary.get("total_usdt", 0.0)

    status_text = "✅ Оплачено"
    await callback.answer(f"Статус обновлён: {status_text}", show_alert=False)

    # Update the message to reflect new status (remove buttons)
    if callback.message:
        original_text = callback.message.text or callback.message.caption or ""
        updated_text = original_text + f"\n\n<b>Статус: {status_text}</b>"
        try:
            await callback.message.edit_text(updated_text, reply_markup=None)
        except Exception:
            pass

    # Notify the designer
    try:
        admin_info = await bot.get_chat(admin_id)
        admin_name = admin_info.full_name or f"id{admin_id}"
    except Exception:
        admin_name = f"id{admin_id}"

    try:
        await bot.send_message(
            designer_id,
            f"✅ <b>Отчёт оплачен!</b>\n\n"
            f"📅 Дата: <b>{html.escape(report_date)}</b>\n"
            f"💰 Сумма: <b>{total_usdt:.2f} USDT</b>\n"
            f"👤 Подтвердил: {html.escape(admin_name)}",
        )
    except Exception as exc:
        logger.warning("Could not notify designer %s about payment: %s", designer_id, exc)

    # Sync payment status to Google Sheets
    if sheets.is_enabled:
        designer = await db.get_designer(designer_id)
        if designer:
            paid_at = datetime.now(tz=timezone.utc).isoformat()
            paid_by_str = str(admin_id)
            try:
                await sheets.update_payment_status(
                    designer.d7_nick, report_date, "paid", paid_at, paid_by_str, ""
                )
            except Exception as exc:
                logger.error("Sheets payment update failed: %s", exc)

    logger.info(
        "Payment PAID: designer=%s date=%s by admin=%s",
        designer_id, report_date, admin_id,
    )


# ── FSM: admin enters unpaid comment ──────────────────────────────────────


@router.message(PaymentCommentStates.waiting_comment)
async def step_payment_comment(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    sheets: GoogleSheetsExporter,
    bot: Bot,
) -> None:
    user = message.from_user
    if not user:
        return

    # Verify still admin
    if not await db.is_admin(user.id, config.admin_ids):
        await state.clear()
        await message.answer("⛔ Недостаточно прав.")
        return

    comment = (message.text or "").strip()
    if not comment:
        await message.answer(
            "⚠️ Комментарий не может быть пустым. Введите причину или /cancel для отмены."
        )
        return

    data = await state.get_data()
    designer_id: int = data["unpaid_designer_id"]
    report_date: str = data["unpaid_report_date"]
    total_usdt: float = data.get("unpaid_total_usdt", 0.0)

    await state.clear()

    # Update DB with unpaid + comment
    await db.update_payment_status(designer_id, report_date, "unpaid", user.id, comment)

    await message.answer(
        f"⏳ Статус «Не оплачено» сохранён.\n\n"
        f"Дата: <b>{html.escape(report_date)}</b>\n"
        f"Причина: <i>{html.escape(comment)}</i>"
    )

    # Notify the designer
    try:
        await bot.send_message(
            designer_id,
            f"⏳ <b>Отчёт пока не оплачен</b>\n\n"
            f"📅 Дата: <b>{html.escape(report_date)}</b>\n"
            f"💰 Сумма: <b>{total_usdt:.2f} USDT</b>\n"
            f"💬 Причина: <i>{html.escape(comment)}</i>\n\n"
            f"По вопросам обращайтесь к администратору.",
        )
    except Exception as exc:
        logger.warning("Could not notify designer %s about unpaid: %s", designer_id, exc)

    # Sync to Google Sheets
    if sheets.is_enabled:
        designer = await db.get_designer(designer_id)
        if designer:
            try:
                await sheets.update_payment_status(
                    designer.d7_nick, report_date, "unpaid", "", str(user.id), comment
                )
            except Exception as exc:
                logger.error("Sheets unpaid update failed: %s", exc)

    logger.info(
        "Payment UNPAID: designer=%s date=%s by admin=%s comment=%r",
        designer_id, report_date, user.id, comment,
    )


# ── v8: Inline Admin Hub callbacks ─────────────────────────────────────────


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_hub(
    callback: CallbackQuery,
    db: Database,
    config: Config,
) -> None:
    """Route all admin: callback data to the appropriate handler."""
    if not await _check_admin_cb(callback, db, config):
        return

    action = (callback.data or "").removeprefix("admin:")
    await callback.answer()

    # ── Navigation ────────────────────────────────────────────────────────
    if action == "home":
        await _hub_edit_or_send(callback, "🛠 <b>Панель администратора</b>\n\nВыберите раздел:", admin_hub_keyboard())
        return

    if action == "employees":
        await _hub_edit_or_send(callback, "👥 <b>Сотрудники</b>\n\nВыберите подраздел:", admin_employees_keyboard())
        return

    if action == "payments":
        await _hub_edit_or_send(callback, "💸 <b>Выплаты</b>\n\nВыберите подраздел:", admin_payments_keyboard())
        return

    if action == "analytics":
        await _hub_edit_or_send(callback, "📊 <b>Аналитика</b>\n\nВыберите подраздел:", admin_analytics_keyboard())
        return

    if action == "reports":
        await _hub_edit_or_send(callback, "⏰ <b>Отчёты</b>\n\nВыберите подраздел:", admin_reports_keyboard())
        return

    # ── Dashboard ─────────────────────────────────────────────────────────
    if action == "dashboard":
        text = await _build_dashboard_text(db)
        await _hub_edit_or_send(callback, text, back_to_hub_keyboard())
        return

    # ── Employees sub-actions ─────────────────────────────────────────────
    if action == "emp:all":
        text = await _build_employees_text(db, None)
        await _hub_edit_or_send(callback, text, admin_employees_keyboard())
        return

    if action in ("emp:designer", "emp:smm", "emp:reviewer", "emp:project_manager"):
        role = action.split(":")[1]
        text = await _build_employees_text(db, role)
        await _hub_edit_or_send(callback, text, admin_employees_keyboard())
        return

    if action == "emp:rank7":
        text = await _build_ranking_text(db, 7)
        await _hub_edit_or_send(callback, text, admin_employees_keyboard())
        return

    if action == "emp:rank30":
        text = await _build_ranking_text(db, 30)
        await _hub_edit_or_send(callback, text, admin_employees_keyboard())
        return

    # ── Payment sub-actions ───────────────────────────────────────────────
    if action == "pay:pending":
        text = await _build_pending_text(db)
        await _hub_edit_or_send(callback, text, admin_payments_keyboard())
        return

    if action == "pay:today":
        text = await _build_paid_text(db, days=1, label="сегодня")
        await _hub_edit_or_send(callback, text, admin_payments_keyboard())
        return

    if action == "pay:week":
        text = await _build_paid_text(db, days=7, label="за 7 дней")
        await _hub_edit_or_send(callback, text, admin_payments_keyboard())
        return

    if action == "pay:history":
        text = (
            "📋 <b>История выплат сотрудника</b>\n\n"
            "Используйте команду:\n"
            "<code>/employeehistory &lt;telegram_id&gt;</code>\n\n"
            "Пример: <code>/employeehistory 123456789</code>"
        )
        await _hub_edit_or_send(callback, text, admin_payments_keyboard())
        return

    # ── Analytics sub-actions ─────────────────────────────────────────────
    if action == "an:today":
        today = moscow_today().isoformat()
        text = await _build_analytics_text(db, today, today, "за сегодня")
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    if action == "an:7d":
        end = moscow_today()
        start = end - timedelta(days=6)
        text = await _build_analytics_text(db, start.isoformat(), end.isoformat(), "за 7 дней")
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    if action == "an:30d":
        end = moscow_today()
        start = end - timedelta(days=29)
        text = await _build_analytics_text(db, start.isoformat(), end.isoformat(), "за 30 дней")
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    if action == "an:geo7":
        end = moscow_today()
        start = end - timedelta(days=6)
        text = await _build_geo_ranking_text(db, start.isoformat(), end.isoformat())
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    if action == "an:roles7":
        end = moscow_today()
        start = end - timedelta(days=6)
        text = await _build_roles_text(db, start.isoformat(), end.isoformat())
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    if action == "an:cpd7":
        end = moscow_today()
        start = end - timedelta(days=6)
        text = await _build_cost_per_day_text(db, start.isoformat(), end.isoformat())
        await _hub_edit_or_send(callback, text, admin_analytics_keyboard())
        return

    # ── Reports sub-actions ───────────────────────────────────────────────
    if action == "rep:missed":
        yesterday = moscow_today() - timedelta(days=1)
        text = await _get_missed_text(db, yesterday)
        await _hub_edit_or_send(callback, text, admin_reports_keyboard())
        return

    if action == "rep:day":
        yesterday = moscow_today() - timedelta(days=1)
        text = await _build_adminreport_text(db, yesterday)
        await _hub_edit_or_send(callback, text, admin_reports_keyboard())
        return

    if action == "rep:schedule":
        text = (
            "ℹ️ <b>Логика напоминаний</b>\n\n"
            "🕗 <b>08:00 МСК</b> — личное напоминание каждому сотруднику сдать отчёт до 12:00 МСК\n\n"
            "🕛 <b>12:00 МСК</b> — сводка администраторам: кто не сдал отчёт за вчера"
        )
        await _hub_edit_or_send(callback, text, admin_reports_keyboard())
        return


# ── Hub helper: edit message or send new ──────────────────────────────────


async def _hub_edit_or_send(
    callback: CallbackQuery,
    text: str,
    markup,
) -> None:
    """Try to edit the existing message; fall back to sending a new one."""
    try:
        if callback.message:
            await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        if callback.message:
            await callback.message.answer(text, reply_markup=markup)


# ── Builder helpers ────────────────────────────────────────────────────────


async def _build_dashboard_text(db: Database) -> str:
    """Build the dashboard text (same as /dashboard command)."""
    today_msk = datetime.now(tz=_MOSCOW).date()
    yesterday = today_msk - timedelta(days=1)
    week_start = today_msk - timedelta(days=6)

    role_counts = await db.count_designers_by_role()
    total_employees = role_counts.get("__total__", 0)
    designer_count = role_counts.get("designer", 0)
    smm_count = role_counts.get("smm", 0)
    reviewer_count = role_counts.get("reviewer", 0)
    project_manager_count = role_counts.get("project_manager", 0)

    pending = await db.get_pending_payments_summary()

    paid_today_rows = await db.get_paid_summary(today_msk)
    paid_today_sum = sum(float(r[4]) for r in paid_today_rows)
    paid_today_count = len(paid_today_rows)

    paid_week_rows = await db.get_paid_summary(week_start)
    paid_week_sum = sum(float(r[4]) for r in paid_week_rows)
    paid_week_count = len(paid_week_rows)

    missing = await db.list_missing_reports(yesterday)
    missed_count = len(missing)

    analytics_today = await db.get_analytics_summary(today_msk.isoformat(), today_msk.isoformat())
    analytics_week = await db.get_analytics_summary(week_start.isoformat(), today_msk.isoformat())

    lines: list[str] = [
        "📌 <b>DASHBOARD</b>",
        f"📅 <code>{html.escape(today_msk.isoformat())}</code> (МСК)\n",
        "━━━━━━━━━━━━━━━━━━━━",
        "👥 <b>Сотрудники</b>",
        f"  Всего: <b>{total_employees}</b>",
        f"  🎨 Дизайнеров: {designer_count}",
        f"  📱 SMM: {smm_count}",
        f"  ⭐ Отзовиков: {reviewer_count}",
        f"  🗂 Проджектов: {project_manager_count}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💸 <b>Оплаты</b>",
        f"  ⏳ Ожидают: <b>{pending['count']} зап. / {pending['total_usdt']:.2f} USDT</b>",
        f"  ✅ Выплачено сегодня: {paid_today_count} зап. / <b>{paid_today_sum:.2f} USDT</b>",
        f"  📈 Выплачено за 7 дн: {paid_week_count} зап. / <b>{paid_week_sum:.2f} USDT</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"⏰ <b>Не сдали за вчера ({html.escape(yesterday.isoformat())}):</b> {missed_count} чел.",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📉 <b>Аналитика сегодня</b>",
        f"  💰 {analytics_today['total_usdt']:.2f} USDT ({analytics_today['task_count']} задач)",
        f"  🌍 GEO: {analytics_today['geo_usdt']:.2f} USDT",
        f"  🎨 Visual: {analytics_today['visual_usdt']:.2f} USDT",
        "",
        "📈 <b>Аналитика 7 дней</b>",
        f"  💰 {analytics_week['total_usdt']:.2f} USDT ({analytics_week['task_count']} задач)",
        f"  🌍 GEO: {analytics_week['geo_usdt']:.2f} USDT",
        f"  🎨 Visual: {analytics_week['visual_usdt']:.2f} USDT",
    ]
    return "\n".join(lines)


async def _build_employees_text(db: Database, role: str | None) -> str:
    designers = await db.list_designers_by_role(role)
    if role:
        role_label = ROLE_LABELS.get(role, role)
        header = f"👥 <b>Сотрудники — {html.escape(role_label)} ({len(designers)}):</b>"
    else:
        header = f"👥 <b>Список сотрудников ({len(designers)}):</b>"

    if not designers:
        return header + "\n\nНикого не найдено."

    entries: list[str] = [header]
    for d in designers:
        role_lbl = ROLE_LABELS.get(d.role, d.role) if d.role else "—"
        tg_ref = f"@{html.escape(d.username)}" if d.username else f"id{d.telegram_id}"
        entries.append(
            f"\n• <b>{html.escape(d.d7_nick)}</b> ({tg_ref})"
            f" — {html.escape(role_lbl)}"
            f"\n  💳 <code>{html.escape(d.wallet)}</code>"
        )

    text = "\n".join(entries)
    # Truncate gracefully if too long for inline edit
    if len(text) > 3800:
        text = text[:3750] + "\n\n<i>…список обрезан, используйте /listdesigners</i>"
    return text


async def _build_ranking_text(db: Database, days: int) -> str:
    ranking = await db.get_employee_ranking(days)
    if not ranking:
        return f"🏆 <b>Рейтинг за {days} дней</b>\n\nДанных пока нет."

    lines = [f"🏆 <b>Рейтинг сотрудников за {days} дней</b>\n"]
    for i, emp in enumerate(ranking, 1):
        role_lbl = ROLE_LABELS.get(emp["role"], emp["role"]) if emp["role"] else "—"
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
        lines.append(
            f"{medal} <b>{html.escape(emp['d7_nick'])}</b> ({html.escape(role_lbl)})\n"
            f"   💰 {emp['total_usdt']:.2f} USDT  •  {emp['task_count']} задач"
        )
    return "\n".join(lines)


async def _build_pending_text(db: Database) -> str:
    rows = await db.get_pending_payments()
    if not rows:
        return "✅ Нет ожидающих оплаты отчётов.\n\n<i>Используйте /pendingpayments для управления оплатой.</i>"

    total_sum = sum(float(r[5]) for r in rows)
    lines = [
        f"⏳ <b>Ожидают оплаты: {len(rows)} записей</b>",
        f"💰 Сумма: <b>{total_sum:.2f} USDT</b>\n",
        "<i>Для подтверждения оплаты используйте /pendingpayments</i>",
        "",
    ]
    for designer_id, d7_nick, wallet, report_date, task_count, total_usdt in rows[:10]:
        wallet_s = html.escape(str(wallet))
        short_wallet = f"{wallet_s[:4]}…{wallet_s[-4:]}" if len(wallet_s) > 10 else wallet_s
        lines.append(
            f"• <b>{html.escape(str(d7_nick))}</b> | {html.escape(str(report_date))}\n"
            f"  {task_count} зад. / {float(total_usdt):.2f} USDT | <code>{short_wallet}</code>"
        )
    if len(rows) > 10:
        lines.append(f"\n<i>…и ещё {len(rows) - 10} записей</i>")
    return "\n".join(lines)


async def _build_paid_text(db: Database, days: int, label: str) -> str:
    from collections import defaultdict
    today_msk = datetime.now(tz=_MOSCOW).date()
    since_date = today_msk - timedelta(days=days - 1)
    rows = await db.get_paid_summary(since_date)
    if not rows:
        return f"💸 Нет оплаченных отчётов {html.escape(label)}."

    total_sum = sum(float(r[4]) for r in rows)
    total_entries = sum(int(r[3]) for r in rows)
    lines = [
        f"✅ <b>Выплачено {html.escape(label)}:</b>",
        f"  {total_entries} записей / <b>{total_sum:.2f} USDT</b>\n",
    ]
    by_nick: dict = defaultdict(lambda: {"entries": 0, "sum": 0.0})
    for _, d7_nick, report_date, task_count, total_usdt in rows:
        by_nick[d7_nick]["entries"] += task_count
        by_nick[d7_nick]["sum"] += total_usdt
    for nick, info in sorted(by_nick.items()):
        lines.append(
            f"👤 <b>{html.escape(nick)}</b> — {info['entries']} зад. / {info['sum']:.2f} USDT"
        )
    return "\n".join(lines)


async def _build_analytics_text(db: Database, start_date: str, end_date: str, label: str) -> str:
    summary = await db.get_analytics_summary(start_date, end_date)
    geo_breakdown = await db.get_geo_breakdown(start_date, end_date)

    lines = [
        f"📊 <b>Аналитика {html.escape(label)}</b>",
        f"📅 <code>{html.escape(start_date)}</code> — <code>{html.escape(end_date)}</code>\n",
        f"💰 <b>Общая сумма: {summary['total_usdt']:.2f} USDT</b>",
        f"🌍 GEO creatives: <b>{summary['geo_usdt']:.2f} USDT</b>",
        f"🎨 Visuals: <b>{summary['visual_usdt']:.2f} USDT</b>",
        f"📋 Всего задач: {summary['task_count']}",
    ]
    if geo_breakdown:
        lines.append("\n🗺 <b>Разбивка по GEO:</b>")
        for item in geo_breakdown:
            lines.append(
                f"  • {html.escape(item['geo'] or '—')}: <b>{item['usdt']:.2f} USDT</b> ({item['count']} зад.)"
            )
    elif summary["task_count"] == 0:
        lines.append("\n<i>Данных за период не найдено.</i>")
    return "\n".join(lines)


async def _build_geo_ranking_text(db: Database, start_date: str, end_date: str) -> str:
    rows = await db.get_geo_ranking(start_date, end_date)
    if not rows:
        return "🗺 <b>Топ по GEO (7 дней)</b>\n\nДанных пока нет."

    lines = ["🗺 <b>Топ по GEO — 7 дней</b> (по сумме)\n"]
    for i, item in enumerate(rows, 1):
        lines.append(
            f"{i}. <b>{html.escape(item['geo'])}</b> — {item['total_usdt']:.2f} USDT ({item['task_count']} зад.)"
        )
    return "\n".join(lines)


async def _build_roles_text(db: Database, start_date: str, end_date: str) -> str:
    rows = await db.get_role_spend_breakdown(start_date, end_date)
    if not rows:
        return "👔 <b>Топ по ролям (7 дней)</b>\n\nДанных пока нет."

    lines = ["👔 <b>Топ по ролям — 7 дней</b> (по сумме)\n"]
    for i, item in enumerate(rows, 1):
        role_lbl = ROLE_LABELS.get(item["role"], item["role"]) if item["role"] else "—"
        lines.append(
            f"{i}. <b>{html.escape(role_lbl)}</b> — {item['total_usdt']:.2f} USDT ({item['task_count']} зад.)"
        )
    return "\n".join(lines)


async def _build_cost_per_day_text(db: Database, start_date: str, end_date: str) -> str:
    rows = await db.get_cost_per_day_breakdown(start_date, end_date)
    if not rows:
        return "💵 <b>Стоимость дня (7 дней)</b>\n\nДанных пока нет."

    lines = [
        "💵 <b>Стоимость дня по направлению — 7 дней</b>\n",
        "<i>Формула: общая сумма / кол-во уникальных дней</i>\n",
    ]
    for item in rows:
        lines.append(
            f"• <b>{html.escape(item['geo'])}</b>: {item['cost_per_day']:.2f} USDT/день"
            f"  <i>({item['total_usdt']:.2f} USDT / {item['day_count']} дн.)</i>"
        )
    return "\n".join(lines)


async def _build_adminreport_text(db: Database, report_date: date) -> str:
    """Build admin report text for a given date."""
    rows = await db.list_tasks_by_date(report_date)
    date_str_safe = html.escape(report_date.isoformat())
    if not rows:
        return f"📊 За <b>{date_str_safe}</b> задач не найдено."

    lines: list[str] = [f"📊 <b>Отчёт за {date_str_safe}</b>\n"]
    current_nick: str | None = None
    day_total = 0.0
    total = 0.0
    current_payment: str = "pending"

    for d7_nick, wallet, task_code, cost_usdt, payment_status in rows:
        nick_safe = html.escape(str(d7_nick))
        wallet_safe = html.escape(str(wallet))
        code_safe = html.escape(str(task_code))

        if d7_nick != current_nick:
            if current_nick is not None:
                pay_icon = _payment_icon(current_payment)
                lines.append(f"  <i>Итого: {day_total:.2f} USDT {pay_icon}</i>")
            current_nick = d7_nick
            current_payment = payment_status or "pending"
            day_total = 0.0
            lines.append(f"\n👤 <b>{nick_safe}</b> (<code>{wallet_safe}</code>)")
        else:
            if payment_status == "pending":
                current_payment = "pending"
            elif payment_status == "unpaid" and current_payment != "pending":
                current_payment = "unpaid"

        lines.append(f"  • <code>{code_safe}</code> — {cost_usdt:.2f} USDT")
        day_total += cost_usdt
        total += cost_usdt

    if current_nick is not None:
        pay_icon = _payment_icon(current_payment)
        lines.append(f"  <i>Итого: {day_total:.2f} USDT {pay_icon}</i>")

    lines.append(f"\n💰 <b>Итого за день: {total:.2f} USDT</b>")
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3750] + "\n\n<i>…используйте /adminreport для полного отчёта</i>"
    return text


# ── helpers ────────────────────────────────────────────────────────────────


def _payment_icon(status: str) -> str:
    if status == "paid":
        return "✅"
    if status == "unpaid":
        return "❌"
    return "⏳"


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks by newline without cutting mid-line."""
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        if current_len + len(line) + 1 > max_len and current:
            parts.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        parts.append("\n".join(current))
    return parts
