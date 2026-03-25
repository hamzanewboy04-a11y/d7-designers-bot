# CHANGES.md — Список изменений

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
