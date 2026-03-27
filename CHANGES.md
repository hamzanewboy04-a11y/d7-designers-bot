# CHANGES.md — Список изменений

## v8.1 — Детальное админ-уведомление + robustness Google Sheets

### 1. Детальный список задач в уведомлении администратора (handlers/report.py)

- Уведомление о новом отчёте теперь показывает полный список задач:
  каждая строка — `• TASK_CODE — X.XX USDT`
- Добавлены поля: 💳 Кошелёк, 📋 Задачи, 📦 Всего задач
- Общая сумма и статус оплаты сохранены

### 2. Устойчивость Google Sheets (sheets.py / append_report_rows)

- Лист `reports` создаётся автоматически если он отсутствует
- Заголовок пишется ровно один раз (только когда A1 пуст) — нет дублирования
- Строки всегда выравниваются по текущему заголовку через словарь col_idx — нет смещений колонок
- Используется `value_input_option="USER_ENTERED"` для корректной записи чисел и дат



## v8 — Inline Admin Hub, расширенная аналитика

### 1. Упрощённое главное меню (keyboards.py)

- Постоянная клавиатура для обычных пользователей: только 4 кнопки:
  `📝 Сдать отчёт`, `👤 Мой профиль`, `📋 Мои задачи`, `✏️ Редактировать профиль`
- Для администраторов добавлена единственная дополнительная кнопка: `🛠 Админка`
- Все старые admin reply-кнопки убраны из persistent keyboard (константы сохранены для обратной совместимости)
- Новая константа `BTN_ADMIN_HUB = "🛠 Админка"`

### 2. Inline Admin Hub (keyboards.py + admin.py)

- По кнопке `🛠 Админка` открывается inline-меню с 5 разделами:
  `📌 Dashboard`, `👥 Сотрудники`, `💸 Выплаты`, `📊 Аналитика`, `⏰ Отчёты`
- Каждый раздел — отдельное inline submenu с кнопкой `🔙 Назад` (возврат в hub)
- Навигация полностью inline: основной раздел ↔ подменю ↔ контент ↔ назад
- Новые функции клавиатур: `admin_hub_keyboard()`, `admin_employees_keyboard()`,
  `admin_payments_keyboard()`, `admin_analytics_keyboard()`, `admin_reports_keyboard()`,
  `back_to_hub_keyboard()`

### 3. Секции Inline Admin Hub (admin.py)

**Dashboard** — сводка (идентично /dashboard)

**Сотрудники:**
- Все сотрудники / Дизайнеры / SMM / Отзовики
- Рейтинг 7 дней / Рейтинг 30 дней (топ по сумме и кол-ву задач, медали 🥇🥈🥉)

**Выплаты:**
- Ожидают оплаты (с кратким списком + инструкция /pendingpayments для действий)
- Выплачено сегодня / Выплачено 7 дней
- История сотрудника → инструкция `/employeehistory <telegram_id>`

**Аналитика:**
- Сегодня / 7 дней / 30 дней
- Топ по GEO 7 дней — страны по сумме убыв.
- Топ по ролям 7 дней — designer/smm/reviewer по сумме убыв.
- Стоимость дня 7 дней — `total_sum / count(distinct report_date)` по каждому GEO

**Отчёты:**
- Кто не сдал вчера
- Отчёт за день (вчера)
- Напоминание логика — информационный текст про 08:00 и 12:00 МСК

### 4. Новые методы DB (db.py)

- `get_employee_ranking(days: int)` — рейтинг сотрудников за период (сумма + задачи)
- `get_role_spend_breakdown(start_date, end_date)` — разбивка расходов по ролям
- `get_geo_ranking(start_date, end_date)` — топ GEO по сумме
- `get_cost_per_day_breakdown(start_date, end_date)` — стоимость дня по GEO

### 5. Callback routing (admin.py)

- Единый роутер `cb_admin_hub` на `admin:*` callback data
- Все действия: навигация, данные, подменю — в одном обработчике с чистым dispatch
- `_hub_edit_or_send()` — надёжное редактирование/отправка с fallback

### 6. Безопасность вывода

- Все пользовательские строки проходят через `html.escape()`
- Длинные тексты обрезаются с подсказкой использовать slash-команду
- Нет parse_mode конфликтов

### 7. Старые slash-команды сохранены

- Все `/dashboard`, `/listdesigners`, `/adminreport`, `/pendingpayments`,
  `/missedreports`, `/paidtoday`, `/paidweek`, `/employeehistory`,
  `/analyticsday`, `/analyticsweek`, `/analyticsmonth`, `/analyticsfrom` — работают как прежде
- Обработчики reply-кнопок в common.py убраны только для старых admin кнопок (которые убраны из клавиатуры)

### 8. Синтаксическая проверка

- Все основные файлы прошли `python3 -m py_compile`:
  `db.py`, `bot.py`, `config.py`, `keyboards.py`, `scheduler.py`, `sheets.py`,
  `handlers/__init__.py`, `handlers/admin.py`, `handlers/common.py`,
  `handlers/register.py`, `handlers/report.py`, `main.py` — ✅ без ошибок.

---

## v7 — Строгие коды задач, аналитика, dashboard

### 1. Строгая валидация кодов задач (report.py)

- Допустимые префиксы: `OTHER`, `PERU1`, `PERU2`, `ITALY`, `ARG`, `CHILE`, `V`
- Формат: `<PREFIX>-<числа>`, например `OTHER-1234`, `V-1001`
- При неверном префиксе — дружелюбная ошибка:
  `❌ PERUU-123 25 — неизвестный префикс. Допустимо: OTHER, PERU1, PERU2, ITALY, ARG, CHILE, V`
- `ParsedTask` содержит `task_code`, `cost_usdt`, `task_prefix`, `task_group`, `task_geo`
- Группы: `OTHER/PERU1/PERU2/ITALY/ARG/CHILE` → `task_group=geo, task_geo=<prefix>`; `V` → `task_group=visual, task_geo=""`

### 2. DB/schema (db.py)

- В таблицу `reports` добавлены поля: `task_prefix`, `task_group`, `task_geo`
- Безопасная миграция через `ALTER TABLE ADD COLUMN` при отсутствии колонок
- `add_task()` сохраняет все три новых поля
- `TaskEntry` расширен: `task_prefix`, `task_group`, `task_geo`
- Новые методы аналитики:
  - `get_analytics_summary(start_date, end_date)` — total/geo/visual USDT + task_count
  - `get_geo_breakdown(start_date, end_date)` — разбивка по GEO
  - `get_group_breakdown(start_date, end_date)` — разбивка по группам
- Новые helper-методы:
  - `count_designers_by_role()` — количество сотрудников по ролям
  - `get_pending_payments_summary()` — count + total_usdt pending

### 3. Google Sheets (sheets.py)

- Заголовок листа `reports` теперь включает: `task_prefix`, `task_group`, `task_geo`
- `append_report_rows()` принимает `list[ParsedTask]` и записывает новые поля
- Общее количество колонок увеличено до 13

### 4. Аналитические команды (admin.py)

- `/analyticsday` — аналитика за сегодня
- `/analyticsweek` — аналитика за 7 дней
- `/analyticsmonth` — аналитика за 30 дней
- `/analyticsfrom YYYY-MM-DD YYYY-MM-DD` — за произвольный период
- Каждая команда показывает: общая сумма, GEO creatives, Visuals, разбивка по GEO

### 5. Dashboard (admin.py)

- Команда `/dashboard` — сводный текстовый дашборд в одном сообщении
- Выводит: сотрудников всего и по ролям, pending payments, paid today/week, пропустившие вчера, аналитику сегодня/неделю

### 6. Новые кнопки в меню администратора (keyboards.py)

- `📊 Dashboard` → `/dashboard`
- `📉 Аналитика день` → `/analyticsday`
- `📈 Аналитика 7 дней` → `/analyticsweek`
- `🗓 Аналитика 30 дней` → `/analyticsmonth`
- Константы: `BTN_ADMIN_DASHBOARD`, `BTN_ADMIN_ANALYTICS_DAY`, `BTN_ADMIN_ANALYTICS_WEEK`, `BTN_ADMIN_ANALYTICS_MONTH`

### 7. Обработчики кнопок (common.py)

- `btn_admin_dashboard` → `cmd_dashboard`
- `btn_admin_analytics_day` → `cmd_analyticsday`
- `btn_admin_analytics_week` → `cmd_analyticsweek`
- `btn_admin_analytics_month` → `cmd_analyticsmonth`

### 8. Синтаксическая проверка

- Все основные файлы прошли `python3 -m py_compile`:
  `db.py`, `bot.py`, `config.py`, `keyboards.py`, `scheduler.py`, `sheets.py`,
  `handlers/__init__.py`, `handlers/admin.py`, `handlers/common.py`,
  `handlers/register.py`, `handlers/report.py`, `main.py` — ✅ без ошибок.

---

## v6 — Логика утреннего дедлайна, история выплат, фильтры ролей, новые кнопки

### 1. Логика дедлайна (08:00 / 12:00 МСК)

**Контекст:**
- Сотрудники выполняют задачи за день и сдают отчёт утром следующего дня (за вчера).
- Дедлайн: 12:00 МСК.

**Изменения:**
- `scheduler.py` разбит на 3 независимых задания в часовом поясе `Europe/Moscow`:
  1. `daily_admin_summary` — ежедневный сводный отчёт (configurable, по умолчанию 08:00 UTC)
  2. `morning_reminder_job` — **08:00 МСК**: отправляет каждому зарегистрированному сотруднику личное сообщение:
     > «Доброе утро! Напоминаю, что отчёт за вчера нужно сдать сегодня до 12:00 МСК. Если отчёт не будет сдан до дедлайна, выплата переносится на следующий день.»
  3. `missed_reports_job` — **12:00 МСК**: собирает список сотрудников без отчёта за вчера и отправляет **только администраторам** (сотрудникам ничего не отправляется).
- Файл: `d7_bot/scheduler.py`

### 2. /report — UX по умолчанию «за вчера»

- Вводный текст явно указывает: «Обычно вы сдаёте отчёт за вчера».
- Кнопки выбора даты переупорядочены: первая — ✅ Вчера (highlighted), затем Сегодня, затем Другая дата.
- Файл: `d7_bot/handlers/report.py`, `d7_bot/keyboards.py`

### 3. /missedreports

- Новая команда: показывает, кто не сдал отчёт за вчера.
- Только для администраторов.
- Та же логика используется в 12:00 МСК рассылке.
- Файл: `d7_bot/handlers/admin.py`

### 4. /employeehistory <telegram_id>

- Новая команда для администраторов.
- Показывает: роль, всего оплачено (записей + сумма), всего pending, всего unpaid.
- Последние 10 оплаченных/неоплаченных записей с датами.
- Файл: `d7_bot/handlers/admin.py`

### 5. /listdesigners с фильтром по роли

- Команда принимает необязательный аргумент: `designer`, `smm`, `reviewer`.
- Примеры: `/listdesigners`, `/listdesigners smm`, `/listdesigners reviewer`.
- Роли показываются с русскими названиями: Дизайнер / SMM / Отзовик.
- Файл: `d7_bot/handlers/admin.py`, `d7_bot/keyboards.py` (словарь `ROLE_LABELS`)

### 6. /paidtoday и /paidweek

- `/paidtoday` — сколько оплачено сегодня (по МСК), сумма, разбивка по сотрудникам.
- `/paidweek` — то же за последние 7 дней.
- Файл: `d7_bot/handlers/admin.py`

### 7. Новые кнопки в меню администратора

- ✅ Выплачено сегодня → `/paidtoday`
- 📈 Выплачено за неделю → `/paidweek`
- ⏰ Не сдали до 12:00 → `/missedreports`
- Файл: `d7_bot/keyboards.py`, `d7_bot/handlers/common.py`

### 8. Новые методы DB

- `has_report_for_date(designer_id, report_date)` — есть ли отчёт за дату.
- `list_missing_reports(report_date)` — список сотрудников без отчёта за дату.
- `get_employee_payment_history(designer_id)` — история выплат сотрудника.
- `get_paid_summary(since_date)` — оплаченные записи начиная с даты (МСК offset UTC+3).
- `list_designers_by_role(role)` — фильтрация сотрудников по роли.
- Файл: `d7_bot/db.py`

### 9. Синтаксическая проверка

- Все основные файлы прошли `python3 -m py_compile`:
  `db.py`, `bot.py`, `config.py`, `keyboards.py`, `scheduler.py`, `sheets.py`,
  `handlers/__init__.py`, `handlers/admin.py`, `handlers/common.py`,
  `handlers/register.py`, `handlers/report.py`, `main.py` — ✅ без ошибок.

---

## v5 — Роли, упрощённая регистрация, комментарии к оплате, уведомления

### 1. Упрощена регистрация (убраны форматы/направления)

- Регистрация теперь: **ник → роль → кошелёк → подтверждение**
- Шаг выбора форматов полностью убран
- Роль выбирается инлайн-кнопками:
  - 🎨 Дизайнер
  - 📱 SMM
  - ⭐ Отзовик
- Файлы: `d7_bot/handlers/register.py`, `d7_bot/keyboards.py`

### 2. Обновлена БД — поле role

- В `Designer` добавлено поле `role: str`
- В таблице `designers` добавлена колонка `role TEXT NOT NULL DEFAULT ''`
- Безопасная миграция через `ALTER TABLE ... ADD COLUMN role` (если отсутствует)
- Старая колонка `formats_json` сохранена физически, но больше не используется в интерфейсе
- `upsert_designer` и `get_designer` работают с `role` вместо `formats`
- Файл: `d7_bot/db.py`

### 3. Обновлена БД — поле payment_comment

- В таблице `reports` добавлена колонка `payment_comment TEXT DEFAULT ''`
- Безопасная миграция при старте бота
- `update_payment_status()` принимает необязательный `payment_comment: str = ""`
- Файл: `d7_bot/db.py`

### 4. Обновлён Google Sheets

- Лист `designers`: колонка `formats` заменена на `role`
- Лист `reports`: добавлена колонка `payment_comment` в заголовок новых листов
- `sync_designers()` выгружает `role` вместо форматов
- `update_payment_status()` принимает и записывает `payment_comment`
- Файл: `d7_bot/sheets.py`

### 5. Уведомление сотруднику об оплате

- При нажатии ✅ Оплачено сотруднику отправляется сообщение:
  - Отчёт за дату оплачен
  - Сумма USDT
  - Кто подтвердил (full_name из Telegram)
- Файл: `d7_bot/handlers/admin.py` — функция `_process_paid()`

### 6. Запрос комментария при "Не оплачено"

- Нажатие ⏳ Не оплачено **не сохраняет статус сразу**
- Бот запрашивает у администратора текстовый комментарий (причину)
- Добавлено FSM-состояние `PaymentCommentStates.waiting_comment`
- В FSM сохраняется: `designer_id`, `report_date`, `total_usdt`, `origin_message_id`
- После ввода комментария:
  - Статус `unpaid` сохраняется в БД вместе с `payment_comment`
  - Google Sheets обновляется
  - Сотруднику отправляется сообщение с причиной
- Файл: `d7_bot/handlers/admin.py` — `PaymentCommentStates`, `step_payment_comment()`

### 7. Обновлены все интерфейсы

- `/me` показывает поле «Роль» вместо форматов
- `/listdesigners` показывает роль вместо форматов
- `/start` обновлён (без упоминания форматов)
- Главное меню: кнопка «👥 Дизайнеры» переименована в «👥 Сотрудники»
- Файлы: `d7_bot/handlers/common.py`, `d7_bot/handlers/admin.py`, `d7_bot/keyboards.py`

### 8. Очистка кода

- Удалён `AVAILABLE_FORMATS` и `build_formats_keyboard` из keyboards.py
- Удалены все импорты и ссылки на форматы в register.py, common.py, admin.py
- Scheduler: `fake_designer` использует `role=""` вместо `formats=[]`
- Файлы: `d7_bot/keyboards.py`, `d7_bot/handlers/register.py`, `d7_bot/scheduler.py`

### 9. Синтаксическая проверка

- Все основные файлы прошли `python -m py_compile`:
  `db.py`, `bot.py`, `config.py`, `keyboards.py`, `scheduler.py`, `sheets.py`,
  `handlers/__init__.py`, `handlers/admin.py`, `handlers/common.py`,
  `handlers/register.py`, `handlers/report.py`, `main.py` — ✅ без ошибок.

---

## v4 — Payment workflow, bugfixes, HTML-safety

### 1. Payment workflow (оплата отчётов)

**Новые поля в БД** (`reports` table):
- `payment_status TEXT DEFAULT 'pending'` — статус оплаты: `pending` / `paid` / `unpaid`
- `paid_at TEXT` — дата/время оплаты (UTC ISO)
- `paid_by INTEGER` — Telegram ID администратора, отметившего оплату

**Миграция:**
- Существующие таблицы автоматически мигрируются (`ALTER TABLE ... ADD COLUMN`) при старте бота.
- Новые задачи создаются со статусом `pending` по умолчанию.

**Уведомления админам:**
- После отправки дизайнером отчёта (принятые задачи) все администраторы получают уведомление:
  - Имя дизайнера, дата, кол-во задач, сумма USDT, кошелёк
  - Inline-кнопки: `✅ Оплачено` / `⏳ Не оплачено`
- Нажатие кнопки обновляет `payment_status` для всех задач этого дизайнера за эту дату в БД.
- Сообщение редактируется — кнопки убираются, добавляется статус.
- Статус синхронизируется в Google Sheets (колонки `payment_status`, `paid_at`, `paid_by`).

**Файлы:** `d7_bot/db.py`, `d7_bot/handlers/admin.py`, `d7_bot/handlers/report.py`,
`d7_bot/keyboards.py`, `d7_bot/sheets.py`

### 2. Новая команда /pendingpayments

- Показывает все отчёты со статусом `pending` (сгруппированы по дизайнеру + дате)
- Для каждого — карточка с кнопками оплаты
- Доступна только администраторам
- Файл: `d7_bot/handlers/admin.py`, `d7_bot/db.py`

### 3. Кнопка «💸 Ожидают оплаты» в меню админа

- Добавлена в `main_menu_keyboard(is_admin=True)` как отдельная строка
- Обработчик в `common.py` → вызывает `cmd_pendingpayments`
- Файл: `d7_bot/keyboards.py`, `d7_bot/handlers/common.py`

### 4. Исправлен баг /listdesigners с несколькими дизайнерами

- **Причина:** при сборке чанков шаблон `"\n".join(chunk)` смешивал заголовок и записи
  без разделителя; при двух и более дизайнерах структура разъезжалась.
- **Исправление:** переработана логика сборки — каждая запись добавляется как отдельный
  элемент с явным переносом `"\n" + entry`; длина считается правильно.
- Все данные дизайнеров экранируются через `html.escape()` — никаких поломок из-за
  спецсимволов в никнеймах/кошельках.
- Файл: `d7_bot/handlers/admin.py`

### 5. Исправлен и улучшен /adminreport

- **Причина поломок:** использование `parse_mode="Markdown"` для Telegram — любой символ
  `_`, `*`, `` ` ``, `[` в никнеймах/кодах задач вызывал ошибку парсинга.
- **Исправление:** полностью переведён на HTML + `html.escape()` для всех пользовательских данных.
- Добавлен иконка статуса оплаты (⏳/✅/❌) после итоговой суммы каждого дизайнера.
- Длинные отчёты автоматически разбиваются на чанки ≤4000 символов.
- Файл: `d7_bot/handlers/admin.py`

### 6. HTML-безопасность во всех хендлерах

- `d7_bot/handlers/admin.py` — весь вывод через `html.escape()` (ники, кошельки, коды задач)
- `d7_bot/handlers/report.py` — ошибочные строки экранируются перед вставкой в `<code>`
- `d7_bot/scheduler.py` — никнеймы и коды задач экранируются в ежедневном отчёте
- Удалён `parse_mode="Markdown"` во всех местах — повсеместно HTML

### 7. Google Sheets: новые колонки для отчётов

- При создании листа `reports` добавляются колонки: `payment_status`, `paid_at`, `paid_by`
- Новые строки заполняются со статусом `pending`
- При смене статуса оплаты — ячейки обновляются через `update_payment_status()`
- Файл: `d7_bot/sheets.py`

### 8. Синтаксическая проверка

- Все основные файлы прошли `python -m ast` / `ast.parse()`:
  `db.py`, `bot.py`, `config.py`, `keyboards.py`, `scheduler.py`, `sheets.py`,
  `handlers/__init__.py`, `handlers/admin.py`, `handlers/common.py`,
  `handlers/register.py`, `handlers/report.py`, `main.py` — ✅ без ошибок.

---

## v3 — UX-улучшения, кнопки меню, автосинк Google Sheets

### 1. Удалены поля "опыт" и "портфолио"
- Из датакласса `Designer` удалены `experience` и `portfolio`
- В `db.py` добавлен метод `migrate()`: при наличии старых столбцов — безопасное пересоздание таблицы через `CREATE new + INSERT + DROP old`
- SQL-схема обновлена — столбцы `experience`, `portfolio_json` убраны
- Файлы: `d7_bot/db.py`

### 2. Регистрация упрощена до 4 шагов
- Убраны шаги `experience` и `portfolio` из `RegisterStates`
- Поток: ник → форматы (инлайн toggle) → кошелёк → подтверждение
- Улучшен UX: при toggle форматов показывается popup-подтверждение выбора
- Файл: `d7_bot/handlers/register.py`

### 3. Главное меню (ReplyKeyboardMarkup)
- Добавлена постоянная клавиатура внизу чата с 4 кнопками:
  `📝 Сдать отчёт` | `👤 Мой профиль` | `📋 Мои задачи` | `✏️ Редактировать профиль`
- Показывается после /start, после завершения любого действия, после ошибок
- Файл: `d7_bot/keyboards.py` — функция `main_menu_keyboard()`

### 4. Выбор даты в /report
- В начале отчёта показываются инлайн-кнопки: `📅 Сегодня`, `📅 Вчера`, `📆 Другая дата…`
- При "Другая дата" — запрашивается ввод YYYY-MM-DD с валидацией
- Дата сохраняется в FSM и используется при записи задач
- Файл: `d7_bot/handlers/report.py`, `d7_bot/keyboards.py` — функция `date_keyboard()`

### 5. Выбор периода в /myreports
- Перед показом задач отображаются кнопки: `7 дней` | `14 дней` | `30 дней`
- По умолчанию — 7 дней (выбирается кнопкой)
- Файл: `d7_bot/handlers/common.py`, `d7_bot/keyboards.py` — функция `period_keyboard()`

### 6. Обработчики кнопок главного меню
- Добавлены хендлеры текстовых кнопок ReplyKeyboard в `common.py`:
  - `📝 Сдать отчёт` → запускает `cmd_report`
  - `👤 Мой профиль` → запускает `cmd_me`
  - `📋 Мои задачи` → запускает `cmd_myreports`
  - `✏️ Редактировать профиль` → запускает `cmd_register`
- Файл: `d7_bot/handlers/common.py`

### 7. Улучшена команда /me
- Показывает красивую карточку профиля с эмодзи
- Кошелёк маскируется: `Txxx…xxxx` (первые 4 + последние 4 символа)
- Добавлена статистика за 7 дней: количество задач и сумма USDT
- Файл: `d7_bot/handlers/common.py`

### 8. db.py — метод get_designer_stats
- Новый метод `get_designer_stats(designer_id, days=7) -> dict`
- Возвращает `{"task_count": int, "total_usdt": float}`
- Используется в /me и может использоваться везде
- Файл: `d7_bot/db.py`

### 9. Google Sheets — автоматическая выгрузка
- При старте бота — `sync_designers()` (таблица сразу актуальна)
- При каждой регистрации/обновлении профиля — `sync_designers()`
- При каждом успешном отчёте — `append_report_rows()`
- Ошибки sheets только логируются, бот не падает
- Файлы: `d7_bot/bot.py`, `d7_bot/handlers/register.py`, `d7_bot/handlers/report.py`

### 10. sheets.py — обновлён формат таблицы дизайнеров
- Убраны столбцы `experience` и `portfolio` из листа "designers"
- Добавлен столбец `updated_at`
- Файл: `d7_bot/sheets.py`

### 11. Fallback-обработчик неизвестных сообщений
- Если пользователь пишет что-то вне FSM — вежливый ответ + показ меню
- Если пользователь в FSM — сообщение игнорируется (не мешает вводу)
- Файл: `d7_bot/handlers/common.py`

### 12. UX-улучшения
- Все сообщения переведены на HTML parse_mode (вместо Markdown)
- Все сообщения структурированы, с эмодзи
- Ошибки содержат понятное объяснение и подсказку
- Успешные действия содержат подтверждение и следующий шаг
- Команда /start показывает разные приветствия для новых и вернувшихся пользователей
- Файлы: все handlers

### 13. bot.py — порядок роутеров
- Роутеры регистрируются в правильном порядке: `register` → `report` → `admin` → `common`
- `common` последний, так как содержит fallback-хендлер для всех сообщений

---

## Исправленные баги

### 1. scheduler_job: исправлена дата отчёта
- **Было:** `date.today()` — отчёт строился за текущий день
- **Стало:** `date.today() - timedelta(days=1)` — отчёт за вчера (корректное поведение, так как задания сдаются в течение дня)
- Файл: `d7_bot/scheduler.py`

### 2. /addadmin: исправлена проверка прав
- **Было:** проверялись только `config.admin_ids` (статичный список из .env)
- **Стало:** проверяется `await db.is_admin()`, который учитывает и `config.admin_ids`, и записи в таблице `admins` в БД
- Файл: `d7_bot/handlers/admin.py`

### 3. Дубликаты задач
- **Было:** одна и та же задача могла быть добавлена несколько раз
- **Стало:**
  - В таблице `reports` добавлен `UNIQUE(designer_id, report_date, task_code)`
  - В `Database` добавлен метод `task_exists(designer_id, report_date, task_code) -> bool`
  - `add_task()` теперь возвращает `bool` (True = добавлено, False = дубликат)
  - При дублировании пользователь получает предупреждение `⚠️`
- Файл: `d7_bot/db.py`, `d7_bot/handlers/report.py`

### 4. Регистрация: шаг подтверждения
- **Было:** шаг `confirm` в FSM отсутствовал/был сломан
- **Стало:** добавлен отдельный State `confirm` — бот показывает полную сводку данных с кнопками «✅ Да, всё верно» / «✏️ Нет, изменить»; при отказе регистрация сбрасывается
- Файл: `d7_bot/handlers/register.py`, `d7_bot/keyboards.py`

### 5. sheets.py: исправлен async-контекст и логика заголовков
- **Было:** синхронные вызовы `gspread` напрямую из `async def` блокировали event loop; логика проверки заголовка была некорректной
- **Стало:**
  - Все операции `gspread` обёрнуты в `asyncio.get_event_loop().run_in_executor(None, callable)`
  - Логика заголовка: если ячейка A1 пуста — пишем заголовок
  - Добавлен вспомогательный метод `_get_or_create_worksheet`
- Файл: `d7_bot/sheets.py`

---

## Новые функции

### 6. Команда /cancel
- Доступна всем пользователям в любой момент
- Сбрасывает FSM-состояние и возвращает в главное меню
- Файл: `d7_bot/handlers/common.py`

### 7. Команда /myreports
- Дизайнер видит свои задачи за последние 7 дней с разбивкой по дням и итогами
- Добавлен метод `list_tasks_by_designer(designer_id, days=7)` в `Database`
- Файл: `d7_bot/handlers/common.py`, `d7_bot/db.py`

### 8. Inline-кнопки выбора форматов
- В шаге `formats` регистрации используются inline-кнопки с toggle ✅/☑️
- Кнопка «Готово ➡️» завершает выбор
- Callback data: `fmt_toggle:<название>` и `fmt_done`
- Файл: `d7_bot/keyboards.py`, `d7_bot/handlers/register.py`

### 9. Валидация TRC20-кошелька
- При регистрации кошелёк проверяется: начинается с `T`, длина 34, только base58-символы
- Regex: `^T[base58chars]{33}$`
- Файл: `d7_bot/handlers/register.py`

### 10. Команда /listdesigners (только администраторы)
- Выводит список всех зарегистрированных дизайнеров: ник, @username/id, форматы, кошелёк
- Длинный список разбивается на несколько сообщений
- Файл: `d7_bot/handlers/admin.py`

### 11. Команда /adminreport [YYYY-MM-DD] (только администраторы)
- Выводит детализированный отчёт за любую дату (по умолчанию — вчера)
- Показывает задачи по каждому дизайнеру с подитогами и общей суммой
- Файл: `d7_bot/handlers/admin.py`

### 12. Логирование через logging
- Все модули используют `logging.getLogger(__name__)`
- В `bot.py` настроен `basicConfig` с уровнем INFO
- Логируются: инициализация, регистрация дизайнеров, добавление администраторов, ошибки Sheets
- Файлы: все модули

---

## Рефакторинг

### Структура проекта
- Разделение хендлеров на 4 файла:
  - `handlers/common.py` — /start, /cancel, /me, /myreports
  - `handlers/register.py` — FSM регистрации
  - `handlers/report.py` — FSM отчёта
  - `handlers/admin.py` — /addadmin, /listdesigners, /adminreport
- Новые модули:
  - `keyboards.py` — `build_formats_keyboard()`, `build_confirm_keyboard()`
  - `scheduler.py` — `scheduler_job()`, `setup_scheduler()`
- `bot.py` сведён к функции `main()`: инициализация зависимостей, регистрация роутеров, запуск

### config.py
- Добавлена поддержка `GOOGLE_SERVICE_ACCOUNT_JSON` как пути к файлу или inline JSON

### db.py
- Добавлен `UNIQUE`-constraint на таблицу `reports`
- Добавлен индекс `idx_reports_designer`
- Добавлены методы: `task_exists()`, `list_tasks_by_designer()`, `is_admin()`
- Вспомогательная функция `_row_to_designer()`

### Новые файлы
- `requirements.txt` с фиксированными зависимостями
- `.env.example` с описанием переменных окружения
