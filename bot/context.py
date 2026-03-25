"""Управление контекстом сессии."""
from typing import Any, Optional
from datetime import datetime
from aiogram.fsm.context import FSMContext
from bot.database import (
    start_new_session,
    save_session_message,
    get_session_history,
    get_session_info,
    load_user_slots,
    save_user_slots,
    update_user_slot,
    load_user_escalation_data,
    save_user_escalation_data,
)


# Стандартные слоты для памяти контекста
CONTEXT_SLOTS = ["city", "budget", "object_type", "goal"]


def _init_escalation_data() -> dict:
    """Инициализация данных эскалации."""
    return {
        "message_count": 0,
        "last_escalation_at": 0,
        "last_button_shown_at": 0,  # v1.3.3
        "button_shown_count": 0,  # v1.3.3
        "user_declined": False
    }


def _init_slots() -> dict:
    """Инициализация слотов памяти."""
    return {
        "city": None,
        "budget": None,
        "object_type": None,
        "goal": None
    }


async def get_session_context(state: FSMContext, user_id: Optional[int] = None) -> dict:
    """
    Получить полный контекст сессии из FSM state.
    Загружает слоты из БД для постоянной памяти (v1.3.2).
    
    Args:
        state: FSM контекст
        user_id: Telegram user ID (опционально, для загрузки слотов из БД)
        
    Returns:
        Словарь с контекстом сессии
    """
    data = await state.get_data()
    
    # Инициализация структуры контекста, если её нет
    if "collected_data" not in data:
        data["collected_data"] = {}
    if "asked_questions" not in data:
        data["asked_questions"] = []
    if "conversation_history" not in data:
        data["conversation_history"] = []
    if "escalation_data" not in data:
        data["escalation_data"] = _init_escalation_data()
    
    # v1.3.2: Загрузка слотов из БД (постоянная память)
    if user_id and "slots" not in data:
        data["slots"] = load_user_slots(user_id)
    elif "slots" not in data:
        data["slots"] = _init_slots()
    
    # Инициализация collected_data, если её нет
    collected_data = data.get("collected_data", {})
    if "location" not in collected_data:
        collected_data["location"] = {}
    if "budget" not in collected_data:
        collected_data["budget"] = {}
    
    return {
        "selected_section": data.get("selected_section"),
        "collected_data": collected_data,
        "asked_questions": data.get("asked_questions", []),
        "conversation_history": data.get("conversation_history", []),
        "escalation_data": data.get("escalation_data", _init_escalation_data()),
        "slots": data.get("slots", _init_slots()),
    }


async def update_session_context(
    state: FSMContext,
    field: str,
    value: Any,
    asked_question: Optional[str] = None
) -> None:
    """
    Обновить контекст сессии.
    
    Args:
        state: FSM контекст
        field: Поле для обновления (может быть вложенным через точку, например "location.city")
        value: Значение для установки
        asked_question: Ключ вопроса, который был задан (например "city", "property_type")
    """
    data = await state.get_data()
    
    # Инициализация структуры, если её нет
    if "collected_data" not in data:
        data["collected_data"] = {}
    if "asked_questions" not in data:
        data["asked_questions"] = []
    
    collected_data = data["collected_data"]
    
    # Обновление вложенных полей (например "location.city")
    if "." in field:
        parts = field.split(".")
        current = collected_data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    else:
        # Прямое обновление поля
        collected_data[field] = value
    
    # Отметка вопроса как заданного
    if asked_question and asked_question not in data["asked_questions"]:
        data["asked_questions"].append(asked_question)
    
    # Сохранение в state
    await state.update_data(
        collected_data=collected_data,
        asked_questions=data["asked_questions"]
    )


async def is_question_asked(state: FSMContext, question_key: str) -> bool:
    """
    Проверить, был ли задан вопрос.
    
    Args:
        state: FSM контекст
        question_key: Ключ вопроса (например "city", "property_type")
        
    Returns:
        True если вопрос был задан, False иначе
    """
    data = await state.get_data()
    asked_questions = data.get("asked_questions", [])
    return question_key in asked_questions


async def mark_question_asked(state: FSMContext, question_key: str) -> None:
    """
    Отметить вопрос как заданный.
    
    Args:
        state: FSM контекст
        question_key: Ключ вопроса (например "city", "property_type")
    """
    data = await state.get_data()
    
    if "asked_questions" not in data:
        data["asked_questions"] = []
    
    if question_key not in data["asked_questions"]:
        data["asked_questions"].append(question_key)
        await state.update_data(asked_questions=data["asked_questions"])


async def add_to_conversation_history(
    state: FSMContext,
    role: str,
    text: str
) -> None:
    """
    Добавить сообщение в историю разговора.
    
    Args:
        state: FSM контекст
        role: Роль ("U" для пользователя, "B" для бота)
        text: Текст сообщения
    """
    data = await state.get_data()
    
    if "conversation_history" not in data:
        data["conversation_history"] = []
    
    # Ограничение истории (последние 50 сообщений)
    history = data["conversation_history"]
    history.append({"role": role, "text": text})
    
    # Ограничиваем до последних 50 сообщений
    if len(history) > 50:
        history = history[-50:]
    
    await state.update_data(conversation_history=history)


# === Функции для работы со слотами ===

async def update_slot(state: FSMContext, slot_name: str, value: Any, user_id: Optional[int] = None) -> None:
    """
    Обновить значение слота.
    v1.3.2: Сохраняет в БД для постоянной памяти.
    
    Args:
        state: FSM контекст
        slot_name: Имя слота (city, budget, object_type, goal)
        value: Значение слота
        user_id: Telegram user ID (опционально, для сохранения в БД)
    """
    if slot_name not in CONTEXT_SLOTS:
        return
    
    data = await state.get_data()
    slots = data.get("slots", _init_slots())
    slots[slot_name] = value
    await state.update_data(slots=slots)
    
    # v1.3.2: Сохраняем в БД для постоянной памяти
    if user_id:
        update_user_slot(user_id, slot_name, value)


async def get_slots(state: FSMContext, user_id: Optional[int] = None) -> dict:
    """
    Получить все слоты.
    v1.3.2: Загружает из БД если не в памяти.
    
    Args:
        state: FSM контекст
        user_id: Telegram user ID (опционально, для загрузки из БД)
        
    Returns:
        Словарь слотов
    """
    data = await state.get_data()
    slots = data.get("slots")
    
    # v1.3.2: Загружаем из БД если не в памяти
    if not slots and user_id:
        slots = load_user_slots(user_id)
        await state.update_data(slots=slots)
    elif not slots:
        slots = _init_slots()
    
    return slots


async def clear_slots(state: FSMContext) -> None:
    """Очистить все слоты."""
    await state.update_data(slots=_init_slots())


# === Функции для работы с эскалацией ===

async def get_escalation_data(state: FSMContext) -> dict:
    """
    Получить данные эскалации.
    
    Args:
        state: FSM контекст
        
    Returns:
        Словарь с данными эскалации
    """
    data = await state.get_data()
    return data.get("escalation_data", _init_escalation_data())


async def update_escalation_data(state: FSMContext, escalation_data: dict) -> None:
    """
    Обновить данные эскалации.
    
    Args:
        state: FSM контекст
        escalation_data: Новые данные эскалации
    """
    await state.update_data(escalation_data=escalation_data)


async def mark_escalation_declined(state: FSMContext) -> None:
    """Отметить отказ пользователя от эскалации."""
    data = await state.get_data()
    escalation_data = data.get("escalation_data", _init_escalation_data())
    escalation_data["user_declined"] = True
    await state.update_data(escalation_data=escalation_data)


async def increment_message_count(state: FSMContext) -> int:
    """
    Увеличить счётчик сообщений.
    
    Returns:
        Новое значение счётчика
    """
    data = await state.get_data()
    escalation_data = data.get("escalation_data", _init_escalation_data())
    escalation_data["message_count"] = escalation_data.get("message_count", 0) + 1
    await state.update_data(escalation_data=escalation_data)
    return escalation_data["message_count"]


# === Функции для работы с сессиями диалога ===

async def start_dialog_session(
    state: FSMContext,
    user_id: int,
    username: Optional[str],
    section: str
) -> str:
    """
    Начать новую сессию диалога.
    Очищает предыдущую историю и создает новую сессию.
    
    Args:
        state: FSM контекст
        user_id: Telegram user ID
        username: Telegram username
        section: Раздел (rent, deal, market, docs_taxes, question)
        
    Returns:
        session_id новой сессии
    """
    # Создаем сессию в БД
    session_id = start_new_session(user_id, username, section)
    
    # Сохраняем session_id в state и очищаем историю
    await state.update_data(
        current_session_id=session_id,
        session_section=section,
        session_history=[]  # Очищаем историю в памяти
    )
    
    return session_id


async def add_to_session_history(
    state: FSMContext,
    role: str,
    text: str
) -> None:
    """
    Добавить сообщение в историю текущей сессии.
    Сохраняет и в памяти (state), и в БД.
    
    Args:
        state: FSM контекст
        role: Роль ("U" для пользователя, "B" для бота)
        text: Текст сообщения
    """
    data = await state.get_data()
    session_id = data.get("current_session_id")
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    message = {
        "role": role,
        "text": text,
        "timestamp": timestamp
    }
    
    # Добавляем в историю в памяти
    session_history = data.get("session_history", [])
    session_history.append(message)
    await state.update_data(session_history=session_history)
    
    # Сохраняем в БД, если есть сессия
    if session_id:
        save_session_message(session_id, role, text)


async def get_current_session_id(state: FSMContext) -> Optional[str]:
    """
    Получить ID текущей сессии.
    
    Args:
        state: FSM контекст
        
    Returns:
        session_id или None
    """
    data = await state.get_data()
    return data.get("current_session_id")


async def get_session_history_from_state(state: FSMContext) -> list[dict]:
    """
    Получить историю текущей сессии из state.
    
    Args:
        state: FSM контекст
        
    Returns:
        Список сообщений с role, text, timestamp
    """
    data = await state.get_data()
    return data.get("session_history", [])


def format_session_for_file(
    session_info: dict,
    messages: list[dict],
    reason: Optional[str] = None,
    comment: Optional[str] = None
) -> str:
    """
    Форматировать сессию для сохранения в .txt файл.
    
    Args:
        session_info: Информация о сессии (section, started_at, user_id, username)
        messages: Список сообщений
        reason: Причина репорта
        comment: Комментарий к репорту
        
    Returns:
        Отформатированный текст для файла
    """
    section = session_info.get("section", "unknown")
    started_at = session_info.get("started_at", "unknown")
    user_id = session_info.get("user_id", "unknown")
    username = session_info.get("username", "N/A")
    
    # Форматируем дату
    if started_at and started_at != "unknown":
        try:
            dt = datetime.fromisoformat(started_at)
            started_at = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    
    lines = [
        f"Session: {section}",
        f"Started: {started_at}",
        f"User: {user_id} (@{username})" if username else f"User: {user_id}",
    ]
    
    if reason:
        lines.append(f"Report reason: {reason}")
    if comment:
        lines.append(f"Comment: {comment}")
    
    lines.append("")
    lines.append("--- Conversation ---")
    lines.append("")
    
    # Форматируем сообщения
    for i, msg in enumerate(messages):
        role_name = "User" if msg["role"] == "U" else "Bot"
        timestamp = msg.get("timestamp", "")
        text = msg.get("text", "")
        
        # Помечаем последний ответ бота как зарепорченный
        is_last_bot = (
            msg["role"] == "B" and 
            i == len(messages) - 1 or
            (i < len(messages) - 1 and messages[i + 1]["role"] == "U" and 
             all(m["role"] == "U" for m in messages[i + 1:]))
        )
        
        # Простая логика: последний ответ бота - это зарепорченный
        is_reported = msg["role"] == "B" and i == len(messages) - 1
        
        if is_reported:
            lines.append(f"[{timestamp}] {role_name}:  <-- REPORTED")
        else:
            lines.append(f"[{timestamp}] {role_name}:")
        lines.append(text)
        lines.append("")
    
    return "\n".join(lines)
