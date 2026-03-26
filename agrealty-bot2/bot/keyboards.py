"""Keyboard layouts for the bot."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bot.texts import (
    MENU_RENT,
    MENU_BUY_SELL,
    MENU_ANALYTICS,
    MENU_DOCS_TAXES,
    MENU_ABOUT_SPECIALIST,
)


def get_main_menu() -> ReplyKeyboardMarkup:
    """Create main menu keyboard with 5 buttons (legacy, для обратной совместимости)."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_RENT)],
            [KeyboardButton(text=MENU_BUY_SELL)],
            [KeyboardButton(text=MENU_ANALYTICS)],
            [KeyboardButton(text=MENU_DOCS_TAXES)],
            [KeyboardButton(text=MENU_ABOUT_SPECIALIST)],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_main_menu_inline() -> InlineKeyboardMarkup:
    """Create main menu inline keyboard with callback buttons."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Аренда", callback_data="menu_rent")],
            [InlineKeyboardButton(text="💰 Покупка и продажа", callback_data="menu_buysell")],
            [InlineKeyboardButton(text="📊 Аналитика и рынок", callback_data="menu_analytics")],
            [InlineKeyboardButton(text="📄 Документы и налоги", callback_data="menu_docs")],
            [InlineKeyboardButton(text="❓ Другое / Задать вопрос", callback_data="menu_other")],
        ]
    )
    return keyboard


def get_feedback_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard with feedback buttons."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 Полезно", callback_data="fb:up"),
                InlineKeyboardButton(text="👎 Некорректно", callback_data="fb:down"),
            ]
        ]
    )
    return keyboard


def get_cancel_kb() -> ReplyKeyboardMarkup:
    """Create keyboard with cancel button."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )
    return keyboard


def get_rent_submenu() -> InlineKeyboardMarkup:
    """Create inline keyboard for rent submenu (take/give) - legacy, для обратной совместимости."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Снять", callback_data="rent:take"),
                InlineKeyboardButton(text="Сдать", callback_data="rent:give"),
            ]
        ]
    )
    return keyboard


def get_rent_submenu_inline() -> InlineKeyboardMarkup:
    """Create inline keyboard for rent submenu according to TZ."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Снять", callback_data="rent_find")],
            [InlineKeyboardButton(text="📤 Сдать", callback_data="rent_list")],
            [InlineKeyboardButton(text="← Назад", callback_data="menu_main")],
        ]
    )
    return keyboard


def get_deal_submenu() -> InlineKeyboardMarkup:
    """Create inline keyboard for deal submenu (buy/sell) - legacy, для обратной совместимости."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Купить", callback_data="deal:buy"),
                InlineKeyboardButton(text="Продать", callback_data="deal:sell"),
            ]
        ]
    )
    return keyboard


def get_buysell_submenu_inline() -> InlineKeyboardMarkup:
    """Create inline keyboard for buy/sell submenu according to TZ."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏡 Купить", callback_data="buy")],
            [InlineKeyboardButton(text="💼 Продать", callback_data="sell")],
            [InlineKeyboardButton(text="← Назад", callback_data="menu_main")],
        ]
    )
    return keyboard


def get_about_submenu() -> InlineKeyboardMarkup:
    """Create inline keyboard for about/specialist submenu."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="О компании", callback_data="about:info"),
                InlineKeyboardButton(text="Связь со специалистом", callback_data="about:specialist"),
            ]
        ]
    )
    return keyboard


def get_feedback_reasons_kb() -> InlineKeyboardMarkup:
    """Create inline keyboard for feedback reasons."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ ошибка фактов", callback_data="fb:reason:facts")],
            [InlineKeyboardButton(text="🤷 непонятно", callback_data="fb:reason:unclear")],
            [InlineKeyboardButton(text="⚠️ опасный / сомнительный совет", callback_data="fb:reason:risky")],
            [InlineKeyboardButton(text="📝 другое", callback_data="fb:reason:other")],
        ]
    )
    return keyboard


def get_admin_panel_kb(
    show_prompt: bool = False,
    prompt_only: bool = False,
) -> InlineKeyboardMarkup:
    """Админ-панель (минимальная): доступ к управлению промптом."""
    if prompt_only:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤖 Промпт GPT (CORE)", callback_data="admin:prompt")],
            ]
        )
    buttons: list[list[InlineKeyboardButton]] = []
    if show_prompt:
        buttons.append([InlineKeyboardButton(text="🤖 Промпт GPT (CORE)", callback_data="admin:prompt")])
    return InlineKeyboardMarkup(inline_keyboard=buttons or [[InlineKeyboardButton(text="🤖 Промпт GPT (CORE)", callback_data="admin:prompt")]])


def get_prompt_admin_kb() -> InlineKeyboardMarkup:
    """Меню управления CORE system prompt."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Показать целиком", callback_data="admin:prompt:full")],
            [InlineKeyboardButton(text="📥 Скачать .txt", callback_data="admin:prompt:download")],
            [InlineKeyboardButton(text="✏️ Заменить", callback_data="admin:prompt:edit")],
            [InlineKeyboardButton(text="« В админ-панель", callback_data="admin:prompt:back")],
        ]
    )