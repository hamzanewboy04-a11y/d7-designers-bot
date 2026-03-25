from __future__ import annotations

import html
import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from d7_bot.config import Config
from d7_bot.db import Database
from d7_bot.keyboards import payment_keyboard
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="admin")


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


@router.message(Command("listdesigners"))
async def cmd_listdesigners(message: Message, db: Database, config: Config) -> None:
    if not await _check_admin(message, db, config):
        return

    designers = await db.list_designers()
    if not designers:
        await message.answer("Дизайнеров пока нет.")
        return

    header = f"👥 <b>Список дизайнеров ({len(designers)}):</b>\n"
    entries: list[str] = []
    for d in designers:
        formats_str = html.escape(", ".join(d.formats)) if d.formats else "—"
        nick_safe = html.escape(d.d7_nick)
        wallet_safe = html.escape(d.wallet)
        if d.username:
            tg_link = f"@{html.escape(d.username)}"
        else:
            tg_link = f"id{d.telegram_id}"
        entries.append(
            f"• <b>{nick_safe}</b> ({tg_link})\n"
            f"  Форматы: {formats_str}\n"
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
        report_date = date.today() - timedelta(days=1)
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
        # Split by designer blocks
        for chunk in _split_text(text, 4000):
            await message.answer(chunk)


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


# ── Payment callback ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("pay:"))
async def cb_payment(
    callback: CallbackQuery, db: Database, config: Config, sheets: GoogleSheetsExporter
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
    await db.update_payment_status(designer_id, report_date, status, admin_id)

    status_text = "✅ Оплачено" if status == "paid" else "⏳ Не оплачено"
    await callback.answer(f"Статус обновлён: {status_text}", show_alert=False)

    # Update the message to reflect new status (remove buttons)
    if callback.message:
        original_text = callback.message.text or callback.message.caption or ""
        updated_text = original_text + f"\n\n<b>Статус: {status_text}</b>"
        try:
            await callback.message.edit_text(updated_text, reply_markup=None)
        except Exception:
            pass

    # Sync payment status to Google Sheets
    if sheets.is_enabled:
        designer = await db.get_designer(designer_id)
        if designer:
            paid_at = datetime.now(tz=timezone.utc).isoformat() if status == "paid" else ""
            paid_by_str = str(admin_id) if status == "paid" else ""
            try:
                await sheets.update_payment_status(
                    designer.d7_nick, report_date, status, paid_at, paid_by_str
                )
            except Exception as exc:
                logger.error("Sheets payment update failed: %s", exc)

    logger.info(
        "Payment status updated: designer=%s date=%s status=%s by admin=%s",
        designer_id, report_date, status, admin_id,
    )
