"""Utility functions for the bot."""
from collections import deque
from dataclasses import dataclass
from typing import Optional
from aiogram.types import Message
from aiogram.types import InlineKeyboardMarkup


# History storage: user_id -> deque of messages
history_by_user: dict[int, deque] = {}


@dataclass
class BotResponse:
    """Структурированный ответ бота."""
    text: str
    has_useful_content: bool = True
    is_system_message: bool = False
    is_error: bool = False
    topic: str = 'general'  # 'general', 'analytics', 'legal', 'tax'


def is_docs_or_taxes_topic(text: str, selected_section: Optional[str]) -> bool:
    """
    Check if text or selected section is about documents or taxes.
    
    Args:
        text: User's text message
        selected_section: Selected menu section or None
        
    Returns:
        True if topic is about documents/taxes
    """
    if selected_section == "docs_taxes":
        return True
    
    keywords = [
        "налог", "ндфл", "вычет", "декларац", "3-ндфл",
        "документ", "договор", "дду", "выписк", "росреестр",
        "регистрац", "нотариус", "доверенност", "кадастр"
    ]
    
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def add_disclaimer_if_needed(response: BotResponse) -> str:
    """
    Добавить поясняющую фразу к ответу, если нужно.
    
    Запрещено добавлять disclaimer если:
    - is_system_message == True
    - is_error == True
    - has_useful_content == False
    
    Args:
        response: BotResponse объект
        
    Returns:
        Текст ответа с поясняющей фразой (если нужно)
    """
    # Запрещено добавлять disclaimer для системных сообщений, ошибок или если нет полезного контента
    if response.is_system_message or response.is_error or not response.has_useful_content:
        return response.text
    
    # Типы поясняющих фраз по теме
    disclaimers = {
        'general': 'Это справочная информация — в конкретной ситуации детали могут отличаться.',
        'analytics': 'Данные носят ориентировочный характер и не заменяют индивидуальный анализ объекта.',
        'legal': 'Информация носит справочный характер и не является юридической или налоговой консультацией.',
        'tax': 'Информация носит справочный характер и не является юридической или налоговой консультацией.',
    }
    
    disclaimer_text = disclaimers.get(response.topic, disclaimers['general'])
    
    # Удаляем существующие дисклеймеры (старый формат с "Дисклеймер:")
    answer = response.text.strip()
    if "Дисклеймер:" in answer:
        last_disclaimer_pos = answer.rfind("Дисклеймер:")
        if last_disclaimer_pos != -1:
            answer = answer[:last_disclaimer_pos].strip()
    
    # Проверяем, нет ли уже такой же поясняющей фразы
    if disclaimer_text in answer:
        return answer
    
    # Добавляем поясняющую фразу
    if answer:
        return f"{answer}\n\n{disclaimer_text}"
    return disclaimer_text


def ensure_disclaimer(answer: str, disclaimer: str) -> str:
    """
    Ensure disclaimer is present at the end of answer.
    Avoids duplicates.
    
    DEPRECATED: Используйте add_disclaimer_if_needed() с BotResponse вместо этой функции.
    Оставлена для обратной совместимости.
    
    Args:
        answer: Bot's answer text
        disclaimer: Disclaimer text to add
        
    Returns:
        Answer with disclaimer (if not already present)
    """
    answer = answer.strip()
    
    # Check if disclaimer already exists
    if "Дисклеймер:" in answer:
        # Check if it's the same disclaimer (simple check)
        if disclaimer in answer:
            return answer
        # Different disclaimer - replace or add
        # Find last "Дисклеймер:" and everything after
        last_disclaimer_pos = answer.rfind("Дисклеймер:")
        if last_disclaimer_pos != -1:
            # Remove old disclaimer and add new one
            answer = answer[:last_disclaimer_pos].strip()
    
    # Add disclaimer
    if answer:
        return f"{answer}\n\n{disclaimer}"
    return disclaimer


def add_history(user_id: int, role: str, text: str) -> None:
    """
    Add message to user's history.
    
    Args:
        user_id: Telegram user ID
        role: "U" for user, "B" for bot
        text: Message text
    """
    if user_id not in history_by_user:
        history_by_user[user_id] = deque(maxlen=20)
    
    history_by_user[user_id].append((role, text))


def get_last_history(user_id: int, n: int = 10) -> list[str]:
    """
    Get last N messages from user's history.
    
    Args:
        user_id: Telegram user ID
        n: Number of messages to return
        
    Returns:
        List of formatted messages: ["U: ...", "B: ..."]
    """
    if user_id not in history_by_user:
        return []
    
    history = list(history_by_user[user_id])
    last_n = history[-n:] if len(history) > n else history
    
    formatted = []
    for role, text in last_n:
        prefix = "U:" if role == "U" else "B:"
        # Truncate long messages
        text_short = text[:200] + "..." if len(text) > 200 else text
        formatted.append(f"{prefix} {text_short}")
    
    return formatted


def split_long_message(text: str, max_length: int = 3500) -> list[str]:
    """
    Split long message into chunks.
    
    Args:
        text: Message text
        max_length: Maximum length per chunk
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Try to split by paragraphs first
    paragraphs = text.split("\n\n")
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If paragraph itself is too long, split by sentences
            if len(para) > max_length:
                sentences = para.split(". ")
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 2 <= max_length:
                        if current_chunk:
                            current_chunk += ". " + sent
                        else:
                            current_chunk = sent
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sent
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text[:max_length]]


async def send_long(
    message: Message,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> None:
    """
    Send long message split into chunks.
    Reply markup is added only to the last chunk.
    
    Args:
        message: Message object to reply to
        text: Text to send
        reply_markup: Optional inline keyboard (added to last chunk only)
    """
    chunks = split_long_message(text)
    
    for i, chunk in enumerate(chunks):
        # Add reply_markup only to the last chunk
        markup = reply_markup if i == len(chunks) - 1 else None
        await message.answer(chunk, reply_markup=markup)

