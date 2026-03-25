from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from d7_bot.config import load_config
from d7_bot.db import Database, Designer, TaskEntry
from d7_bot.sheets import GoogleSheetsExporter

FORMATS = [
    "Фото",
    "AI-генерация",
    "AI-видео",
    "Photoshop/альт. софт",
    "Видеомонтаж",
    "Генерация иллюстраций",
]


class RegisterStates(StatesGroup):
    d7_nick = State()
    experience = State()
    formats = State()
    portfolio = State()
    wallet = State()


class ReportStates(StatesGroup):
    report_date = State()
    tasks = State()


async def ensure_registered(message: Message, db: Database) -> bool:
    designer = await db.get_designer(message.from_user.id)
    if not designer:
        await message.answer("Вы еще не зарегистрированы. Используйте /register")
        return False
    return True


def registration_summary(data: dict) -> str:
    return (
        "Проверьте данные:\n"
        f"Ник D7: {data['d7_nick']}\n"
        f"Опыт: {data['experience']}\n"
        f"Форматы: {', '.join(data['formats'])}\n"
        f"Портфолио: {', '.join(data['portfolio'])}\n"
        f"Кошелек: {data['wallet']}\n\n"
        "Отправьте `да`, чтобы сохранить, либо начните заново командой /register"
    )


async def build_admin_report(db: Database, on_date: date) -> str:
    rows = await db.list_tasks_by_date(on_date)
    if not rows:
        return f"Отчет за {on_date.isoformat()}: задач нет."

    grouped: dict[str, dict] = defaultdict(lambda: {"wallet": "", "tasks": [], "sum": 0.0})
    total_sum = 0.0
    for nick, wallet, task_code, cost in rows:
        grouped[nick]["wallet"] = wallet
        grouped[nick]["tasks"].append((task_code, cost))
        grouped[nick]["sum"] += cost
        total_sum += cost

    lines = [f"Итоги за {on_date.isoformat()}"]
    for nick, payload in grouped.items():
        lines.append(f"\n👤 {nick} ({payload['wallet']})")
        for code, cost in payload["tasks"]:
            lines.append(f"- {code}: {cost:.2f} USDT")
        lines.append(f"  Итого: {payload['sum']:.2f} USDT")
    lines.append(f"\n💰 Общая сумма: {total_sum:.2f} USDT")
    return "\n".join(lines)


async def setup_handlers(dp: Dispatcher, db: Database, exporter: GoogleSheetsExporter | None, admin_ids: list[int]) -> None:
    @dp.message(Command("start"))
    async def start_cmd(message: Message) -> None:
        await message.answer(
            "Привет! Я бот D7 дизайнеры.\n"
            "Команды:\n/register — регистрация/редактирование\n/report — добавить ежедневный отчет\n/me — показать профиль\n/addadmin <id> — добавить администратора"
        )

    @dp.message(Command("register"))
    async def register_cmd(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(RegisterStates.d7_nick)
        await message.answer("Введите ник на портале D7:")

    @dp.message(RegisterStates.d7_nick)
    async def reg_d7_nick(message: Message, state: FSMContext) -> None:
        await state.update_data(d7_nick=message.text.strip())
        await state.set_state(RegisterStates.experience)
        await message.answer("Опишите опыт в дизайне:")

    @dp.message(RegisterStates.experience)
    async def reg_experience(message: Message, state: FSMContext) -> None:
        await state.update_data(experience=message.text.strip())
        await state.set_state(RegisterStates.formats)
        await message.answer("Укажите форматы через запятую из списка:\n" + ", ".join(FORMATS))

    @dp.message(RegisterStates.formats)
    async def reg_formats(message: Message, state: FSMContext) -> None:
        formats = [x.strip() for x in message.text.split(",") if x.strip()]
        await state.update_data(formats=formats)
        await state.set_state(RegisterStates.portfolio)
        await message.answer("Пришлите до 5 ссылок/файлов портфолио через запятую:")

    @dp.message(RegisterStates.portfolio)
    async def reg_portfolio(message: Message, state: FSMContext) -> None:
        portfolio = [x.strip() for x in message.text.split(",") if x.strip()][:5]
        await state.update_data(portfolio=portfolio)
        await state.set_state(RegisterStates.wallet)
        await message.answer("Укажите USDT TRC20 кошелек:")

    @dp.message(RegisterStates.wallet)
    async def reg_wallet(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        data = await state.get_data()

        if data.get("wallet") and text.casefold() == "да":
            designer = Designer(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                d7_nick=data["d7_nick"],
                experience=data["experience"],
                formats=data["formats"],
                portfolio=data["portfolio"],
                wallet=data["wallet"],
            )
            await db.upsert_designer(designer)
            if exporter:
                await exporter.sync_designers(await db.list_designers())
            await state.clear()
            await message.answer("Профиль сохранен ✅")
            return

        await state.update_data(wallet=text)
        data = await state.get_data()
        await message.answer(registration_summary(data))

    @dp.message(Command("me"))
    async def me_cmd(message: Message) -> None:
        designer = await db.get_designer(message.from_user.id)
        if not designer:
            await message.answer("Профиль не найден. Используйте /register")
            return
        await message.answer(
            f"Ник: {designer.d7_nick}\n"
            f"Опыт: {designer.experience}\n"
            f"Форматы: {', '.join(designer.formats)}\n"
            f"Портфолио: {', '.join(designer.portfolio)}\n"
            f"Кошелек: {designer.wallet}"
        )

    @dp.message(Command("report"))
    async def report_cmd(message: Message, state: FSMContext) -> None:
        if not await ensure_registered(message, db):
            return
        await state.clear()
        await state.set_state(ReportStates.report_date)
        await message.answer("Введите дату отчета в формате YYYY-MM-DD (или `today`):")

    @dp.message(ReportStates.report_date)
    async def report_date_step(message: Message, state: FSMContext) -> None:
        raw = message.text.strip()
        if raw.lower() == "today":
            dt = date.today()
        else:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                await message.answer("Неверный формат даты. Пример: 2026-03-25")
                return
        await state.update_data(report_date=dt.isoformat())
        await state.set_state(ReportStates.tasks)
        await message.answer(
            "Введите задачи построчно в формате `КОД СУММА`, например:\nD7-1001 25\nD7-1002 40.5"
        )

    @dp.message(ReportStates.tasks)
    async def report_tasks_step(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        designer = await db.get_designer(message.from_user.id)
        lines = [line.strip() for line in message.text.splitlines() if line.strip()]
        added = 0
        for line in lines:
            try:
                code, cost_raw = line.split(maxsplit=1)
                cost = float(cost_raw)
            except ValueError:
                continue
            await db.add_task(
                TaskEntry(
                    designer_id=designer.telegram_id,
                    report_date=data["report_date"],
                    task_code=code,
                    cost_usdt=cost,
                )
            )
            added += 1
        if exporter:
            await exporter.append_report_rows(designer, data["report_date"], lines)
        await state.clear()
        await message.answer(f"Сохранено задач: {added}")

    @dp.message(Command("addadmin"))
    async def add_admin_cmd(message: Message) -> None:
        if message.from_user.id not in admin_ids:
            await message.answer("Команда доступна только главным администраторам.")
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Использование: /addadmin <telegram_id>")
            return
        new_admin = int(parts[1])
        await db.add_admin(new_admin)
        await message.answer(f"Администратор {new_admin} добавлен.")


async def scheduler_job(bot: Bot, db: Database) -> None:
    today = date.today()
    report = await build_admin_report(db, today)
    admins = await db.list_admins()
    for admin_id in admins:
        try:
            await bot.send_message(admin_id, report)
        except Exception:
            continue


async def main() -> None:
    config = load_config()
    db = Database(config.db_path)
    await db.init()
    for admin in config.admin_ids:
        await db.add_admin(admin)

    exporter = GoogleSheetsExporter(config.google_sheet_id, config.google_service_account_json)
    if not exporter.is_enabled:
        exporter = None

    bot = Bot(config.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    await setup_handlers(dp, db, exporter, config.admin_ids)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(scheduler_job, CronTrigger(hour=config.report_hour_utc, minute=0), kwargs={"bot": bot, "db": db})
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
