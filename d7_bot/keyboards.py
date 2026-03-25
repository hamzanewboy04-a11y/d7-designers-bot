from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# All available design formats
AVAILABLE_FORMATS: list[str] = [
    "Логотип",
    "Баннер",
    "Социальные сети",
    "Презентация",
    "Полиграфия",
    "UI/UX",
    "Иллюстрация",
    "Моушн",
    "Видео",
    "Другое",
]


def build_formats_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    """
    Build an inline keyboard for format selection.

    Each format shows ✅ if selected or ☑️ if not.
    A "Готово ➡️" button is added at the end.
    Callback data pattern:  "fmt_toggle:<format_name>"
    Done button callback:   "fmt_done"
    """
    buttons: list[list[InlineKeyboardButton]] = []

    for fmt in AVAILABLE_FORMATS:
        icon = "✅" if fmt in selected else "☑️"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {fmt}",
                    callback_data=f"fmt_toggle:{fmt}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="Готово ➡️", callback_data="fmt_done")]
    )

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
