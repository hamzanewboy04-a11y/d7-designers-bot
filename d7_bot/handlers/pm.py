from __future__ import annotations

import html
import logging
from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from d7_bot.config import Config
from d7_bot.db import Database, Employee, moscow_today
from d7_bot.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="pm")


class PmSmmEntryStates(StatesGroup):
    choose_smm = State()
    choose_assignment = State()
    choose_date = State()
    enter_comment = State()


async def _check_pm(message: Message, db: Database, config: Config) -> Employee | None:
    user = message.from_user
    if not user:
        return None

    employee = await db.get_employee_by_telegram_id(user.id)
    is_admin = await db.is_admin(user.id, config.admin_ids)
    if not employee:
        if is_admin:
            return None
        await message.answer("⛔ Профиль сотрудника не найден.")
        return None

    if employee.role != "project_manager" and not is_admin:
        await message.answer("⛔ Только проджект-менеджер или администратор может вносить SMM-отчёты.")
        return None
    return employee


@router.message(Command("pm_smm_report"))
async def cmd_pm_smm_report(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    pm = await _check_pm(message, db, config)
    if not pm:
        return

    smm_employees = await db.list_employees_by_role("smm")
    if not smm_employees:
        await message.answer("ℹ️ В системе пока нет активных SMM-сотрудников.")
        return

    await state.clear()
    await state.set_state(PmSmmEntryStates.choose_smm)

    lines = [
        "🧾 <b>PM → SMM daily entry</b>",
        "",
        "Выбери SMM сотрудника и отправь его <code>ID</code> из списка:",
        "",
    ]
    for employee in smm_employees:
        tg_ref = f"@{html.escape(employee.username)}" if employee.username else f"tg:{employee.telegram_id or '—'}"
        lines.append(
            f"• <b>{html.escape(employee.display_name)}</b> — ID <code>{employee.id}</code> — {tg_ref}"
        )

    await message.answer("\n".join(lines))


@router.message(PmSmmEntryStates.choose_smm)
async def step_choose_smm(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("⚠️ Отправь числовой ID сотрудника из списка.")
        return

    smm_employee = await db.get_employee(int(raw))
    if not smm_employee or smm_employee.role != "smm" or not smm_employee.is_active:
        await message.answer("❌ SMM сотрудник не найден или не активен.")
        return

    assignments = await db.list_active_smm_assignments(smm_employee.id)
    if not assignments:
        await message.answer(
            "⚠️ У этого SMM пока нет активных assignment'ов.\n"
            "Сначала нужно завести каналы и ставки в базе."
        )
        await state.clear()
        return

    await state.update_data(smm_employee_id=smm_employee.id)
    await state.set_state(PmSmmEntryStates.choose_assignment)

    lines = [
        f"✅ SMM: <b>{html.escape(smm_employee.display_name)}</b>",
        "",
        "Теперь отправь <code>ID</code> assignment'а:",
        "",
    ]
    for assignment in assignments:
        lines.append(
            f"• ID <code>{assignment.id}</code> — <b>{html.escape(assignment.channel_name)}</b>"
            f" | {html.escape(assignment.geo or '—')} | {assignment.daily_rate_usdt:.2f} USDT/день"
        )
    await message.answer("\n".join(lines))


@router.message(PmSmmEntryStates.choose_assignment)
async def step_choose_assignment(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()
    smm_employee_id = int(data["smm_employee_id"])

    if not raw.isdigit():
        await message.answer("⚠️ Отправь числовой ID assignment'а.")
        return

    assignments = await db.list_active_smm_assignments(smm_employee_id)
    assignment = next((a for a in assignments if a.id == int(raw)), None)
    if not assignment:
        await message.answer("❌ Assignment не найден среди активных для этого SMM.")
        return

    default_date = (moscow_today() - timedelta(days=1)).isoformat()
    await state.update_data(
        assignment_id=assignment.id,
        assignment_channel=assignment.channel_name,
        assignment_geo=assignment.geo,
        assignment_rate=assignment.daily_rate_usdt,
    )
    await state.set_state(PmSmmEntryStates.choose_date)
    await message.answer(
        f"✅ Assignment: <b>{html.escape(assignment.channel_name)}</b> | {assignment.daily_rate_usdt:.2f} USDT/день\n\n"
        f"Отправь дату в формате <code>YYYY-MM-DD</code>.\n"
        f"Если это отчёт за вчера — просто отправь: <code>{default_date}</code>"
    )


@router.message(PmSmmEntryStates.choose_date)
async def step_choose_date(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        from datetime import date
        parsed = date.fromisoformat(raw)
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй <code>YYYY-MM-DD</code>.")
        return

    await state.update_data(report_date=parsed.isoformat())
    await state.set_state(PmSmmEntryStates.enter_comment)
    await message.answer(
        "Введите комментарий к записи или отправь <code>-</code>, если комментарий не нужен."
    )


@router.message(PmSmmEntryStates.enter_comment)
async def step_enter_comment(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    pm = await _check_pm(message, db, config)
    if not pm:
        await state.clear()
        return

    data = await state.get_data()
    smm_employee = await db.get_employee(int(data["smm_employee_id"]))
    if not smm_employee:
        await state.clear()
        await message.answer("❌ SMM сотрудник не найден.")
        return

    comment_raw = (message.text or "").strip()
    comment = "" if comment_raw == "-" else comment_raw

    entry_id = await db.add_smm_daily_entry_v2(
        smm_employee_id=smm_employee.id,
        entered_by_pm_id=pm.id,
        report_date=str(data["report_date"]),
        assignment_id=int(data["assignment_id"]),
        channel_name_snapshot=str(data["assignment_channel"]),
        geo_snapshot=str(data.get("assignment_geo") or ""),
        daily_rate_snapshot=float(data["assignment_rate"]),
        comment=comment,
    )

    await state.clear()
    await message.answer(
        "✅ <b>SMM daily entry сохранён</b>\n\n"
        f"Сотрудник: <b>{html.escape(smm_employee.display_name)}</b>\n"
        f"Канал: <b>{html.escape(str(data['assignment_channel']))}</b>\n"
        f"Гео: <b>{html.escape(str(data.get('assignment_geo') or '—'))}</b>\n"
        f"Дата: <b>{html.escape(str(data['report_date']))}</b>\n"
        f"Сумма: <b>{float(data['assignment_rate']):.2f} USDT</b>\n"
        f"Entry ID: <code>{entry_id}</code>",
        reply_markup=main_menu_keyboard(is_admin=await db.is_admin(message.from_user.id, config.admin_ids) if message.from_user else False),
    )
