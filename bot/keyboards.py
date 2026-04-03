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


def get_onboarding_key_figures_kb() -> InlineKeyboardMarkup:
    """Create inline keyboard with 'Посмотреть ключевые цифры' button for onboarding."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Посмотреть ключевые цифры", callback_data="onboarding:key_figures")],
        ]
    )
    return keyboard


def get_main_menu_inline() -> InlineKeyboardMarkup:
    """Create main menu inline keyboard with callback buttons."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Аренда", callback_data="menu_rent")],
            [InlineKeyboardButton(text="💰 Покупка и продажа", callback_data="menu_buysell")],
            [InlineKeyboardButton(text="📊 Обзор рынка", callback_data="menu_analytics")],
            [InlineKeyboardButton(text="📄 Документы и налоги", callback_data="menu_docs")],
            [InlineKeyboardButton(text="👤 Подключить специалиста", callback_data="menu_specialist")],
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
    full_admin_tools: bool = False,
) -> InlineKeyboardMarkup:
    """Create admin panel keyboard."""
    if prompt_only:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤖 Промпт GPT (CORE)", callback_data="admin:prompt")],
            ]
        )
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:report")],
        [InlineKeyboardButton(text="📥 Экспорт фидбека", callback_data="admin:export")],
        [InlineKeyboardButton(text="👤 Пользователи", callback_data="admin:users")],
    ]
    if full_admin_tools:
        buttons.append([InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")])
        buttons.append([InlineKeyboardButton(text="👋 Приветствие /start", callback_data="admin:onboarding")])
    if show_prompt:
        buttons.append([InlineKeyboardButton(text="🤖 Промпт GPT (CORE)", callback_data="admin:prompt")])
    if full_admin_tools:
        buttons.append([InlineKeyboardButton(text="👥 Управление админами", callback_data="admin:manage")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_prompt_admin_kb() -> InlineKeyboardMarkup:
    """Меню управления CORE system prompt."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👀 Показать в Telegram", callback_data="admin:prompt:full")],
            [InlineKeyboardButton(text="📥 Скачать .txt", callback_data="admin:prompt:download")],
            [InlineKeyboardButton(text="✏️ Заменить (только .txt)", callback_data="admin:prompt:edit")],
            [InlineKeyboardButton(text="⚙️ Динамика LLM", callback_data="admin:prompt:dyn")],
            [InlineKeyboardButton(text="« В админ-панель", callback_data="admin:prompt:back")],
        ]
    )


def get_prompt_dynamic_kb() -> InlineKeyboardMarkup:
    """Меню редактирования динамических блоков и runtime-конфига."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧩 BLOCK_FEEDBACK", callback_data="admin:prompt:dyn:full:fb")],
            [InlineKeyboardButton(text="💸 BLOCK_PRICING", callback_data="admin:prompt:dyn:full:pr")],
            [InlineKeyboardButton(text="⚖️ BLOCK_RISKS_DOCS", callback_data="admin:prompt:dyn:full:rd")],
            [InlineKeyboardButton(text="👤 BLOCK_SPECIALIST_REQUEST", callback_data="admin:prompt:dyn:full:sp")],
            [InlineKeyboardButton(text="« Назад к CORE", callback_data="admin:prompt")],
        ]
    )


def get_admin_manage_kb() -> InlineKeyboardMarkup:
    """Create admin management keyboard."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:add")],
            [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin:remove")],
            [InlineKeyboardButton(text="📋 Список админов", callback_data="admin:list")],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:back")],
        ]
    )
    return keyboard


def get_onboarding_admin_kb() -> InlineKeyboardMarkup:
    """Меню редактирования текста приветствия /start."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👀 Показать в Telegram", callback_data="admin:onboarding:full")],
            [InlineKeyboardButton(text="📥 Скачать файл", callback_data="admin:onboarding:download")],
            [InlineKeyboardButton(text="✏️ Заменить", callback_data="admin:onboarding:edit")],
            [InlineKeyboardButton(text="« В админ-панель", callback_data="admin:onboarding:back")],
        ]
    )


def get_admin_users_kb() -> InlineKeyboardMarkup:
    """Меню учёта пользователей: список в Telegram и выгрузка .txt."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список в Telegram", callback_data="admin:users:list")],
            [InlineKeyboardButton(text="📥 Скачать .txt", callback_data="admin:users:download")],
            [InlineKeyboardButton(text="« В админ-панель", callback_data="admin:back")],
        ]
    )


def get_export_date_kb() -> InlineKeyboardMarkup:
    """Create keyboard for export date selection."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Сегодня", callback_data="admin:export:today")],
            [InlineKeyboardButton(text="📅 Вчера", callback_data="admin:export:yesterday")],
            [InlineKeyboardButton(text="📋 Всё время", callback_data="admin:export:all")],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:back")],
        ]
    )
    return keyboard


def get_escalation_button() -> InlineKeyboardMarkup:
    """
    v1.3.3: Create inline keyboard with escalation button.
    Кнопка должна быть единственной в сообщении (не комбинировать с feedback).
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Подключить специалиста", callback_data="escalation:confirm")]
        ]
    )
    return keyboard


def get_consultation_request_keyboard() -> InlineKeyboardMarkup:
    """
    Create inline keyboard with consultation request button.
    Показывается когда LLM предлагает консультацию специалиста.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Запросить консультацию", callback_data="consultation:request")]
        ]
    )
    return keyboard