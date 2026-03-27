# D7 Designers Bot

Telegram-бот для команды D7 с учётом сотрудников, ежедневных отчётов, оплат, аналитики и выгрузки в Google Sheets.

## Что умеет бот

### 1. Профили сотрудников
Команда: `/register`

При регистрации сотрудник указывает:
- ник в D7;
- роль;
- TRC20-кошелёк USDT.

Поддерживаемые роли:
- `designer`
- `smm`
- `reviewer`
- `project_manager`

Профиль можно обновлять повторным вызовом `/register`.

### 2. Ежедневные отчёты
Команда: `/report`

По умолчанию бот предлагает сдать отчёт за вчера.

#### Для дизайнеров / SMM / проджектов
Формат ввода — построчно:
```text
OTHER-1234 12.50
PERU1-5678 8.00
V-1001 5.00
```

Поддерживаемые префиксы задач:
- GEO: `OTHER`, `PERU1`, `PERU2`, `ITALY`, `ARG`, `CHILE`
- Visual: `V`

Бот:
- валидирует формат;
- не принимает дубликаты за ту же дату;
- считает сумму;
- отправляет уведомление администраторам.

#### Для отзовиков (`reviewer`)
Отчёт сдаётся отдельным сценарием:
- GEO;
- количество отзывов;
- цена за 1 отзыв;
- подтверждение итога.

### 3. Профиль и история задач
Команды:
- `/me` — профиль сотрудника;
- `/myreports` — задачи за 7 / 14 / 30 дней;
- `/cancel` — отмена текущего сценария.

### 4. Администрирование
Команды:
- `/addadmin <telegram_id>` — добавить администратора;
- `/listdesigners [role]` — список сотрудников, опционально по роли;
- `/adminreport [YYYY-MM-DD]` — отчёт за день;
- `/pendingpayments` — ожидающие оплаты;
- `/employeehistory <telegram_id>` — история выплат сотрудника;
- `/dashboard` — сводный дашборд;
- `/missedreports` — кто не сдал отчёт за вчера;
- `/paidtoday` — выплачено сегодня;
- `/paidweek` — выплачено за 7 дней;
- `/analyticsday` — аналитика за сегодня;
- `/analyticsweek` — аналитика за 7 дней;
- `/analyticsmonth` — аналитика за 30 дней;
- `/analyticsfrom YYYY-MM-DD YYYY-MM-DD` — аналитика за произвольный период.

### 5. PM / SMM skeleton
Начальный PM-only flow для новой SMM-модели:
- `/pm_smm_assign <employee_id> <channel_name> <geo> <daily_rate>` — создать assignment для SMM;
- `/pm_smm_assignments` — посмотреть активные assignment'ы;
- `/pm_smm_report` — внести daily entry за SMM через пошаговый flow;
- `/pm_smm_weekly` — weekly payroll preview по всем SMM за прошлую неделю;
- `/pm_smm_weekly_employee <employee_id>` — детализация по одному SMM за прошлую неделю;
- `/pm_smm_batch_create` — создать weekly payout batch'и по прошлой неделе;
- `/pm_smm_batches` — посмотреть pending SMM weekly batch'и.

> Это переходный skeleton под новую бизнес-логику. Текущий designer flow продолжает работать отдельно.

Также администраторам доступна inline-панель `🛠 Админка` с разделами:
- Dashboard;
- Сотрудники;
- Выплаты;
- Аналитика;
- Отчёты.

### 5. Оплаты
После отправки отчёта администраторы получают сообщение с кнопками:
- `✅ Оплачено`
- `⏳ Не оплачено`

При оплате:
- обновляется статус в БД;
- сотруднику отправляется уведомление;
- при включённой интеграции обновляется Google Sheets.

При статусе `Не оплачено`:
- админ вводит комментарий;
- сотруднику уходит причина;
- комментарий записывается в БД и Sheets.

### 6. Планировщик
В проекте есть 3 плановых сценария:
- ежедневная админ-сводка в `REPORT_HOUR_UTC`;
- 08:00 МСК — напоминание сотрудникам сдать отчёт за вчера;
- 12:00 МСК — уведомление администраторам, кто не сдал отчёт.

### 7. Google Sheets
Если заданы `GOOGLE_SHEET_ID` и `GOOGLE_SERVICE_ACCOUNT_JSON`, бот:
- синхронизирует лист `designers`;
- дописывает отчёты в лист `reports`;
- обновляет статус оплаты в `reports`.

## Стек
- Рекомендуемо: Python 3.11+
- Минимально протестировано локально: Python 3.9.6
- aiogram 3
- aiosqlite
- APScheduler
- gspread
- google-auth
- python-dotenv

## Структура проекта
```text
.
├── main.py
├── requirements.txt
├── README.md
├── CHANGES.md
├── README_UPDATE.md
└── d7_bot/
    ├── __init__.py
    ├── bot.py
    ├── config.py
    ├── db.py
    ├── keyboards.py
    ├── scheduler.py
    ├── sheets.py
    └── handlers/
        ├── __init__.py
        ├── admin.py
        ├── common.py
        ├── register.py
        └── report.py
```

## Конфигурация
Создайте `.env`:

```env
BOT_TOKEN=...
# или TELEGRAM_BOT_TOKEN=...
DB_PATH=d7_bot.sqlite3
ADMIN_IDS=111111111,222222222
REPORT_HOUR_UTC=8

# Опционально Google Sheets
GOOGLE_SHEET_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON={...json...}
```

## Запуск локально
Рекомендуемый вариант:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Если на машине пока есть только системный Python 3.9:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

> Для стабильного dev/prod baseline лучше перейти на Python 3.11+.

## Smoke tests
Минимальный baseline-тест набор запускается стандартным `unittest`:

```bash
python -m unittest discover -s tests -v
```

Если используете локальный venv:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Что сейчас покрыто:
- парсинг task codes;
- базовый smoke по БД;
- дедупликация задач;
- выборка сотрудников по роли.

## Деплой
Минимально для старта нужен только:
- `BOT_TOKEN` или `TELEGRAM_BOT_TOKEN`

Рекомендуемо также задать:
- `ADMIN_IDS`
- `DB_PATH`
- `REPORT_HOUR_UTC`

Для Google Sheets дополнительно:
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
