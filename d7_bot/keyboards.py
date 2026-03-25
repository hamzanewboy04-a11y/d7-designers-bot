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
]

# Text labels for main menu buttons (used to match incoming messages)
BTN_REPORT = "📝 Сдать отчёт"
BTN_PROFILE = "👤 Мой профиль"
BTN_TASKS = "📋 Мои задачи"
BTN_EDIT = "✏️ Редактировать профиль"

BTN_ADMIN_DESIGNERS = "👥 Сотрудники"
BTN_ADMIN_REPORT = "📊 Отчёт за день"
BTN_ADMIN_PENDING = "💸 Ожидают оплаты"

MAIN_MENU_BUTTONS = {BTN_REPORT, BTN_PROFILE, BTN_TASKS, BTN_EDIT}
ADMIN_MENU_BUTTONS = {
    BTN_REPORT, BTN_PROFILE, BTN_TASKS, BTN_EDIT,
    BTN_ADMIN_DESIGNERS, BTN_ADMIN_REPORT, BTN_ADMIN_PENDING,
}


def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown at the bottom of the chat."""
    keyboard = [
        [KeyboardButton(text=BTN_REPORT), KeyboardButton(text=BTN_PROFILE)],
        [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_EDIT)],
    ]
    if is_admin:
        keyboard.append([
            KeyboardButton(text=BTN_ADMIN_DESIGNERS),
            KeyboardButton(text=BTN_ADMIN_REPORT),
        ])
        keyboard.append([
            KeyboardButton(text=BTN_ADMIN_PENDING),
        ])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        persistent=True,
    )


def date_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for report date selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="report_date:today"),
                InlineKeyboardButton(text="📅 Вчера", callback_data="report_date:yesterday"),
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
