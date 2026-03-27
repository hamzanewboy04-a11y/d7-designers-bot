# README_UPDATE.md — Инструкция по применению изменений в GitHub

## Предварительные требования

- У вас есть локальная копия репозитория `d7-designers-bot`
- Установлен `git` и Python 3.11+
- Есть доступ на запись в репозиторий (или право создавать форк и PR)

---

## Шаг 1. Создайте feature-ветку

```bash
cd /путь/к/вашему/репозиторию
git checkout main          # или master — зависит от вашего репо
git pull origin main       # обновите до последней версии
git checkout -b refactor/v2-improved-bot
```

---

## Шаг 2. Скопируйте новые файлы

Скопируйте содержимое директории `/Users/nikitabelyavskiy/.openclaw/workspace/d7-designers-bot/`
в корень вашего репозитория:

```bash
# Пример (замените пути под себя):
SRC=/Users/nikitabelyavskiy/.openclaw/workspace/d7-designers-bot

# Копируем корневые файлы
cp "$SRC/main.py"          ./main.py
cp "$SRC/requirements.txt" ./requirements.txt
cp "$SRC/.env.example"     ./.env.example

# Копируем пакет d7_bot
cp -r "$SRC/d7_bot/"       ./d7_bot/
```

> ⚠️ Это перезапишет существующие файлы. Убедитесь, что у вас нет несохранённых изменений в рабочей копии.

---

## Шаг 3. Проверьте структуру файлов

После копирования структура должна выглядеть так:

```
.
├── main.py
├── requirements.txt
├── .env.example
├── CHANGES.md
├── README_UPDATE.md
└── d7_bot/
    ├── __init__.py
    ├── bot.py
    ├── config.py
    ├── db.py
    ├── sheets.py
    ├── keyboards.py
    ├── scheduler.py
    └── handlers/
        ├── __init__.py
        ├── common.py
        ├── register.py
        ├── report.py
        └── admin.py
```

---

## Шаг 4. Установите зависимости

```bash
# Создайте/обновите виртуальное окружение
python3.11 -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

---

## Шаг 5. Настройте .env

```bash
cp .env.example .env
# Откройте .env в редакторе и заполните значения
nano .env
```

Обязательные поля:
- `BOT_TOKEN` — токен бота от @BotFather
- `ADMIN_IDS` — Telegram ID начальных администраторов через запятую

---

## Шаг 6. Миграция базы данных (если уже есть данные)

Новая версия добавляет `UNIQUE`-constraint и новый индекс в таблицу `reports`.
Если у вас **уже есть БД** с данными, выполните миграцию вручную:

```bash
sqlite3 d7_bot.sqlite3 << 'EOF'
-- Создаём новую таблицу с UNIQUE constraint
CREATE TABLE IF NOT EXISTS reports_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    designer_id INTEGER NOT NULL,
    report_date TEXT NOT NULL,
    task_code TEXT NOT NULL,
    cost_usdt REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (designer_id) REFERENCES designers(telegram_id) ON DELETE CASCADE,
    UNIQUE(designer_id, report_date, task_code)
);

-- Переносим данные (дубликаты будут пропущены через OR IGNORE)
INSERT OR IGNORE INTO reports_new
    (id, designer_id, report_date, task_code, cost_usdt, created_at)
SELECT id, designer_id, report_date, task_code, cost_usdt, created_at
FROM reports;

-- Заменяем таблицу
DROP TABLE reports;
ALTER TABLE reports_new RENAME TO reports;

-- Добавляем индексы
CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
CREATE INDEX IF NOT EXISTS idx_reports_designer ON reports(designer_id);
EOF
```

> ℹ️ Если БД новая (только что созданная), `db.init()` сделает всё автоматически.

---

## Шаг 7. Запустите и протестируйте локально

```bash
python main.py
```

Проверьте:
- [ ] `/start` — приветствие работает
- [ ] `/register` — регистрация с inline-кнопками форматов
- [ ] `/cancel` — отменяет текущий FSM
- [ ] `/report` — сдача задач с проверкой дублей
- [ ] `/myreports` — список задач за 7 дней
- [ ] `/me` — просмотр профиля
- [ ] `/addadmin <id>` — добавление администратора (только для адмнов)
- [ ] `/listdesigners` — список дизайнеров (только для адмнов)
- [ ] `/adminreport 2024-01-15` — отчёт за дату (только для адмнов)

---

## Шаг 8. Создайте коммит и откройте Pull Request

```bash
# Добавьте все новые/изменённые файлы
git add .

# Создайте коммит
git commit -m "refactor: улучшенная версия бота v2

- Исправлены баги: дата в scheduler, /addadmin проверка БД, дубли задач, шаг confirm в регистрации
- Исправлен sheets.py: async-safe вызовы gspread через run_in_executor
- Добавлены: /cancel, /myreports, /listdesigners, /adminreport
- Inline-кнопки для выбора форматов при регистрации
- Валидация TRC20-кошелька
- Рефакторинг: разбивка на модули handlers/, keyboards.py, scheduler.py
- Полное логирование через logging

См. CHANGES.md для детального описания изменений."

# Запушьте ветку
git push origin refactor/v2-improved-bot
```

Затем откройте Pull Request на GitHub:
1. Перейдите в репозиторий на github.com
2. Нажмите **Compare & pull request**
3. Заполните описание (можно вставить содержимое `CHANGES.md`)
4. Назначьте ревьюеров при необходимости
5. Нажмите **Create pull request**

---

## Дополнительно: деплой на сервер

После мержа PR обновите сервер:

```bash
ssh user@your-server
cd /path/to/bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
# Перезапустите сервис (systemd или supervisor)
sudo systemctl restart d7-designers-bot
# или
supervisorctl restart d7-designers-bot
```

---

## Откат изменений (если что-то пошло не так)

```bash
# На сервере
git checkout main
git revert HEAD  # или git reset --hard <предыдущий_коммит>
sudo systemctl restart d7-designers-bot
```
