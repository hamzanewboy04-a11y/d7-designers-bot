from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Available roles for registration
AVAILABLE_ROLES: list[tuple[str, str]] = [
    ("🎨 Дизайнер", "designer"),
    ("📱 SMM", "smm"),
    ("⭐ Отзовик", "reviewer"),
    ("🗂 Проджект-менеджер", "project_manager"),
]

# Human-readable role names (Russian)
ROLE_LABELS: dict[str, str] = {
    "designer": "Дизайнер",
    "smm": "SMM",
    "reviewer": "Отзовик",
    "project_manager": "Проджект-менеджер",
}

# Text labels for main menu buttons (used to match incoming messages)
BTN_REPORT = "📝 Сдать отчёт"
BTN_PROFILE = "👤 Мой профиль"
BTN_TASKS = "📋 Мои задачи"
BTN_EDIT = "✏️ Редактировать профиль"

# v8: single admin hub button
BTN_ADMIN_HUB = "🛠 Админка"

# Legacy admin button constants (kept for backward compat — slash commands still work)
BTN_ADMIN_DESIGNERS = "👥 Сотрудники"
BTN_ADMIN_REPORT = "📊 Отчёт за день"
BTN_ADMIN_PENDING = "💸 Ожидают оплаты"
BTN_ADMIN_PAID_TODAY = "✅ Выплачено сегодня"
BTN_ADMIN_PAID_WEEK = "📈 Выплачено за неделю"
BTN_ADMIN_MISSED = "⏰ Не сдали до 12:00"
BTN_ADMIN_DASHBOARD = "📊 Dashboard"
BTN_ADMIN_ANALYTICS_DAY = "📉 Аналитика день"
BTN_ADMIN_ANALYTICS_WEEK = "📈 Аналитика 7 дней"
BTN_ADMIN_ANALYTICS_MONTH = "🗓 Аналитика 30 дней"

MAIN_MENU_BUTTONS = {BTN_REPORT, BTN_PROFILE, BTN_TASKS, BTN_EDIT}
ADMIN_MENU_BUTTONS = {BTN_REPORT, BTN_PROFILE, BTN_TASKS, BTN_EDIT, BTN_ADMIN_HUB}


# ── Reply keyboards ─────────────────────────────────────────────────────────


def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown at the bottom of the chat.

    v8: admin gets only ONE extra button — 🛠 Админка — instead of the bloated list.
    """
    keyboard = [
        [KeyboardButton(text=BTN_REPORT), KeyboardButton(text=BTN_PROFILE)],
        [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_EDIT)],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN_HUB)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        persistent=True,
    )


# ── Inline admin hub keyboards ──────────────────────────────────────────────


def admin_hub_keyboard() -> InlineKeyboardMarkup:
    """Main admin hub inline menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📌 Dashboard", callback_data="admin:dashboard"),
                InlineKeyboardButton(text="👥 Сотрудники", callback_data="admin:employees"),
            ],
            [
                InlineKeyboardButton(text="💸 Выплаты", callback_data="admin:payments"),
                InlineKeyboardButton(text="📊 Аналитика", callback_data="admin:analytics"),
            ],
            [
                InlineKeyboardButton(text="⏰ Отчёты", callback_data="admin:reports"),
            ],
        ]
    )


def admin_employees_keyboard() -> InlineKeyboardMarkup:
    """Employees submenu inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Все сотрудники", callback_data="admin:emp:all"),
                InlineKeyboardButton(text="🎨 Дизайнеры", callback_data="admin:emp:designer"),
            ],
            [
                InlineKeyboardButton(text="📱 SMM", callback_data="admin:emp:smm"),
                InlineKeyboardButton(text="⭐ Отзовики", callback_data="admin:emp:reviewer"),
            ],
            [
                InlineKeyboardButton(text="🗂 Проджекты", callback_data="admin:emp:project_manager"),
            ],
            [
                InlineKeyboardButton(text="🏆 Рейтинг 7 дней", callback_data="admin:emp:rank7"),
                InlineKeyboardButton(text="🏆 Рейтинг 30 дней", callback_data="admin:emp:rank30"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin:home"),
            ],
        ]
    )


def admin_payments_keyboard() -> InlineKeyboardMarkup:
    """Payments submenu inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏳ Ожидают оплаты", callback_data="admin:pay:pending"),
            ],
            [
                InlineKeyboardButton(text="✅ Выплачено сегодня", callback_data="admin:pay:today"),
                InlineKeyboardButton(text="📈 Выплачено 7 дней", callback_data="admin:pay:week"),
            ],
            [
                InlineKeyboardButton(text="📋 История сотрудника", callback_data="admin:pay:history"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin:home"),
            ],
        ]
    )


def admin_analytics_keyboard() -> InlineKeyboardMarkup:
    """Analytics submenu inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📉 Сегодня", callback_data="admin:an:today"),
                InlineKeyboardButton(text="📈 7 дней", callback_data="admin:an:7d"),
                InlineKeyboardButton(text="🗓 30 дней", callback_data="admin:an:30d"),
            ],
            [
                InlineKeyboardButton(text="🗺 Топ по гео 7 дней", callback_data="admin:an:geo7"),
            ],
            [
                InlineKeyboardButton(text="👔 Топ по ролям 7 дней", callback_data="admin:an:roles7"),
            ],
            [
                InlineKeyboardButton(text="💵 Стоимость дня 7 дней", callback_data="admin:an:cpd7"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin:home"),
            ],
        ]
    )


def admin_reports_keyboard() -> InlineKeyboardMarkup:
    """Reports submenu inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏰ Кто не сдал вчера", callback_data="admin:rep:missed"),
            ],
            [
                InlineKeyboardButton(text="📊 Отчёт за день", callback_data="admin:rep:day"),
            ],
            [
                InlineKeyboardButton(text="ℹ️ Напоминание логика", callback_data="admin:rep:schedule"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin:home"),
            ],
        ]
    )


def back_to_hub_keyboard() -> InlineKeyboardMarkup:
    """Single back-to-hub button, used after showing content in-place."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="admin:home")]
        ]
    )


# ── Report / registration inline keyboards ──────────────────────────────────


def date_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for report date selection.
    Default selection is 'yesterday' (✅ marked) since reports are typically for the previous day.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Вчера", callback_data="report_date:yesterday"),
            ],
            [
                InlineKeyboardButton(text="Сегодня", callback_data="report_date:today"),
            ],
            [
                InlineKeyboardButton(text="📆 Другая дата…", callback_data="report_date:custom"),
            ],
        ]
    )


def period_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for selecting a report period (7/14/30 days)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="7 дней", callback_data="period:7"),
                InlineKeyboardButton(text="14 дней", callback_data="period:14"),
                InlineKeyboardButton(text="30 дней", callback_data="period:30"),
            ]
        ]
    )


def build_role_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for role selection during registration."""
    buttons: list[list[InlineKeyboardButton]] = []
    for label, value in AVAILABLE_ROLES:
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"role_select:{value}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    """Yes / No confirmation keyboard used in registration confirm step."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, всё верно", callback_data="reg_confirm:yes"),
                InlineKeyboardButton(text="✏️ Нет, изменить", callback_data="reg_confirm:no"),
            ]
        ]
    )


def payment_keyboard(designer_id: int, report_date: str) -> InlineKeyboardMarkup:
    """Inline keyboard for admin payment decision."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Оплачено",
                    callback_data=f"pay:paid:{designer_id}:{report_date}",
                ),
                InlineKeyboardButton(
                    text="⏳ Не оплачено",
                    callback_data=f"pay:unpaid:{designer_id}:{report_date}",
                ),
            ]
        ]
    )
