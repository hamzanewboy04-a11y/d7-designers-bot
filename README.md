# D7 Designers Bot

Telegram-бот для команды дизайнеров D7:
- регистрация и редактирование профиля дизайнера;
- ежедневные отчеты по задачам (несколько задач в день);
- ежедневная автосводка администраторам в 08:00 UTC;
- выгрузка дизайнеров и отчетов в Google Sheets.

## Функционал

### 1) Регистрация дизайнера
Команда: `/register`

Поля:
- ник на портале D7;
- опыт в дизайне;
- форматы дизайна (список);
- портфолио (до 5 ссылок/файлов);
- USDT TRC20 кошелек.

Профиль можно перезаписать повторной командой `/register`.

### 2) Ежедневные отчеты
Команда: `/report`

Шаги:
1. Указать дату `YYYY-MM-DD` или `today`.
2. Отправить список задач построчно в формате:
   ```
   D7-1001 25
   D7-1002 40.5
   ```

### 3) Администраторы и сводки
- Первичные админы задаются через `ADMIN_IDS`.
- Добавление админа в runtime: `/addadmin <telegram_id>` (доступно только первичным админам).
- Каждый день в `REPORT_HOUR_UTC` отправляется сводка с:
  - дизайнером;
  - кошельком;
  - задачами;
  - суммами по дизайнеру и общей суммой.

### 4) Google Sheets
Если заданы `GOOGLE_SHEET_ID` и `GOOGLE_SERVICE_ACCOUNT_JSON`, бот:
- синхронизирует лист `designers`;
- дописывает строки в лист `reports`.

## Запуск

1. Установить зависимости:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Создать `.env`:
```env
BOT_TOKEN=...
# альтернативно можно TELEGRAM_BOT_TOKEN=...
DB_PATH=d7_bot.sqlite3
ADMIN_IDS=111111111,222222222
REPORT_HOUR_UTC=8

# Опционально Google Sheets:
GOOGLE_SHEET_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON={...json...}
```

3. Запустить:
```bash
python main.py
```


## Деплой на Railway

1. Подключите репозиторий в Railway: **New Project → Deploy from GitHub Repo**.
2. Укажите стартовую команду: `python main.py` (если Railway не определил автоматически).
3. В разделе **Variables** добавьте переменные:
   - обязательная: `BOT_TOKEN` (или `TELEGRAM_BOT_TOKEN`);
   - рекомендуемые: `REPORT_HOUR_UTC` (например, `8`), `DB_PATH` (например, `d7_bot.sqlite3`);
   - опционально: `ADMIN_IDS` (через запятую, например `111,222`) и переменные Google Sheets.
4. Если используете шаблон `secrets.XYZ`, сначала создайте такой Secret в Railway.
   Иначе указывайте значение напрямую (например, `ADMIN_IDS=111,222`).
5. Перезапустите деплой после сохранения переменных.

Если в логах Railway видно `ValueError: BOT_TOKEN is required`, это означает, что переменная токена не задана или задана с другим именем.
Если видно ошибку `failed to stat ... /secrets/ADMIN_IDS`, значит задана ссылка на несуществующий Secret `ADMIN_IDS`.

## Команды
- `/start`
- `/register`
- `/report`
- `/me`
- `/addadmin <telegram_id>`
