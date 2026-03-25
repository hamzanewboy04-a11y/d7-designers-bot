from __future__ import annotations

import logging
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from d7_bot.db import Database, TaskEntry
from d7_bot.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)
router = Router(name="report")


class ReportStates(StatesGroup):
    tasks = State()


# Expected format per task line: "TASK_CODE COST"
# Example:
#   D7-101 12.50
#   D7-102 8.00


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    designer = await db.get_designer(user.id)
    if not designer:
        await message.answer(
            "❌ Вы не зарегистрированы. Пройдите регистрацию: /register"
        )
        return

    await state.set_state(ReportStates.tasks)
    today = date.today().isoformat()
    await message.answer(
        f"📝 *Отчёт задач за сегодня ({today})*\n\n"
        "Введите задачи в формате:\n"
        "`КОД_ЗАДАЧИ СТОИМОСТЬ_USDT`\n\n"
        "Каждая задача — с новой строки. Пример:\n"
        "```\n"
        "D7-101 12.50\n"
        "D7-102 8.00\n"
        "```\n"
        "_/cancel — отменить_",
        parse_mode="Markdown",
    )


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
        await message.answer("Профиль не найден. Пройдите регистрацию: /register")
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Пустой ввод. Введите задачи или /cancel для отмены.")
        return

    today = date.today().isoformat()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]

    accepted: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []

    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            errors.append(f"  ❌ `{line}` — неверный формат")
            continue
        task_code, cost_str = parts
        try:
            cost_usdt = float(cost_str.replace(",", "."))
            if cost_usdt <= 0:
                raise ValueError("non-positive")
        except ValueError:
            errors.append(f"  ❌ `{line}` — некорректная стоимость")
            continue

        task = TaskEntry(
            designer_id=user.id,
            report_date=today,
            task_code=task_code,
            cost_usdt=cost_usdt,
        )
        added = await db.add_task(task)
        if added:
            accepted.append(line)
        else:
            duplicates.append(f"  ⚠️ `{task_code}` — уже сдана сегодня")

    # Build response
    parts_resp: list[str] = []
    if accepted:
        parts_resp.append(f"✅ Принято задач: {len(accepted)}")
    if duplicates:
        parts_resp.append("Дубликаты (пропущены):\n" + "\n".join(duplicates))
    if errors:
        parts_resp.append("Ошибки:\n" + "\n".join(errors))

    if not accepted and not duplicates and not errors:
        await message.answer("Не удалось разобрать ни одной задачи. Проверьте формат.")
        return

    await state.clear()
    await message.answer("\n\n".join(parts_resp), parse_mode="Markdown")

    # Export accepted lines to Google Sheets
    if accepted and sheets.is_enabled:
        try:
            await sheets.append_report_rows(designer, today, accepted)
        except Exception as exc:
            logger.error("Sheets export failed: %s", exc)

    logger.info(
        "Report from %s (%s): %d accepted, %d duplicates, %d errors",
        designer.d7_nick,
        user.id,
        len(accepted),
        len(duplicates),
        len(errors),
    )
