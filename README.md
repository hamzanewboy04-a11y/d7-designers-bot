# D7 Designers Bot

Telegram-бот и evolving internal ops/payroll system для команды D7.

Проект находится в переходном состоянии:
- legacy designer flow уже рабочий;
- next-gen domain model для SMM / reviewer / payroll уже внедряется;
- часть старых flows сохранена для совместимости.

## Что есть сейчас

### 1. Legacy designer flow
Команда: `/report`

Что работает:
- дизайнер сдаёт отчёт по задачам;
- дата по умолчанию — вчера;
- task codes валидируются;
- дубликаты не принимаются;
- админам приходит отчёт с оплатой;
- есть история, дашборды и аналитика;
- работает Google Sheets export.

### 2. Reviewer main flow
Команда: `/report`

Для роли `reviewer` основной `/report` теперь ведёт в reviewer v2 flow.

Legacy fallback сохранён отдельно:
- `/report_reviews_legacy`

### 3. Reviewer v2
Команды:
- `/report`
- `/report_reviews_v2`

Новый flow для reviewer:
- multi-line report;
- typed items;
- поддержка типов:
  - `small`
  - `large`
  - `custom`
- отдельные quantity / unit_price / total;
- финальный комментарий к отчёту.

### 4. PM verification for reviewer v2
PM / admin команды:
- `/pm_review_queue`
- `/pm_review_verify <entry_id>`
- `/pm_review_reject <entry_id> [comment]`

Что работает:
- очередь pending reviewer entries;
- verify;
- reject;
- уведомление reviewer при reject.

### 5. Reviewer payout batches
PM / admin команды:
- `/pm_review_batch_create`
- `/pm_review_batches`
- `/pm_review_batch_paid <batch_id>`
- `/pm_review_batch_history`

Что работает:
- verified reviewer entries переходят в payout batches;
- pending batch list;
- mark as paid;
- history;
- уведомление reviewer при оплате.

### 6. SMM / PM flow
PM / admin команды:
- `/pm_smm_assign <employee_id> <channel_name> <geo> <daily_rate>`
- `/pm_smm_assignments`
- `/pm_smm_report`
- `/pm_smm_weekly`
- `/pm_smm_weekly_employee <employee_id>`
- `/pm_smm_batch_create`
- `/pm_smm_batches`
- `/pm_smm_batch_paid <batch_id>`
- `/pm_smm_batch_history`

Что работает:
- assignment management;
- PM-only SMM daily entries;
- weekly payroll preview;
- batch creation;
- mark as paid;
- history;
- уведомление SMM при оплате.

### 7. Admin / reporting
Сохранены legacy admin команды:
- `/addadmin <telegram_id>`
- `/listdesigners [role]`
- `/adminreport [YYYY-MM-DD]`
- `/pendingpayments`
- `/employeehistory <telegram_id>`
- `/dashboard`
- `/missedreports`
- `/paidtoday`
- `/paidweek`
- `/analyticsday`
- `/analyticsweek`
- `/analyticsmonth`
- `/analyticsfrom YYYY-MM-DD YYYY-MM-DD`

Также есть inline admin hub `🛠 Админка`.

## Бизнес-модель, которая уже отражена в коде

### Designers
- self-report;
- daily report;
- piecework;
- immediate payment.

### Reviewers
- новый typed report flow v2;
- PM verification;
- payout batches.

### SMM
- self-report не используется;
- daily entries вносит PM;
- assignments + daily rates;
- weekly payout batches.

### Product manager
- operational role;
- ведёт SMM entries;
- верифицирует reviewer entries.

## Стек
- Рекомендуемо: Python 3.11+
- Локально протестировано: Python 3.9.6
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
├── tests/
│   ├── test_db_smoke.py
│   ├── test_nextgen_flows.py
│   └── test_report_parsing.py
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
        ├── pm.py
        ├── register.py
        ├── report.py
        └── reviewer_v2.py
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

Fallback для текущей машины:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Smoke tests
Запуск:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Что покрыто сейчас:
- task parsing;
- legacy DB smoke;
- SMM assignment / daily entry / weekly batch flow;
- reviewer v2 verify / payout batch flow.

## Railway deploy baseline
В репозитории подготовлены:
- `.gitignore`
- `Procfile`
- `runtime.txt`
- `railway.json`

Важно:
- в `railway.json` больше нет жёсткого `startCommand`;
- для multi-service deployment команду запуска нужно задавать в Railway отдельно для каждого сервиса.

Bot service команда запуска:
```bash
python main.py
```

Web admin MVP запускается отдельно:
```bash
uvicorn web.app:app --host 0.0.0.0 --port $PORT
```

Минимальные env для Railway:
- `BOT_TOKEN` или `TELEGRAM_BOT_TOKEN`
- `ADMIN_IDS`
- `DB_PATH`
- `REPORT_HOUR_UTC`

Опционально:
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Важно:
- Railway filesystem эфемерный;
- текущий SQLite-путь подходит для тестового/временного деплоя;
- для нормального production лучше внешний persistent storage или PostgreSQL.

## Текущее состояние

### Уже сделано
- стабилизирован legacy designer/report/admin слой;
- выровнена Moscow date logic в ключевых местах;
- исправлен scheduler Sheets duplication bug;
- добавлена next-gen domain model;
- собран SMM weekly cycle;
- собран reviewer v2 cycle;
- добавлен smoke baseline для next-gen flows.

### Ещё не завершено
- нет web admin panel;
- нет полноценного service/API слоя;
- Railway deploy baseline подготовлен, но production storage ещё не решён;
- проект всё ещё transition-phase.

## Следующие логичные шаги
1. Выделить service layer поверх `db.py`.
2. Подготовить web admin panel groundwork.
3. Решить вопрос persistent storage для Railway / production.
4. Добавить больше тестов на business rules и edge cases.
