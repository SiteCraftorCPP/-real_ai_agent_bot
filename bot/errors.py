"""Централизованная обработка ошибок."""
import logging
from typing import Optional
from bot.utils import BotResponse

logger = logging.getLogger(__name__)


class BotError(Exception):
    """Базовое исключение для ошибок бота."""
    pass


class APITimeoutError(BotError):
    """Ошибка таймаута API."""
    pass


class RateLimitError(BotError):
    """Ошибка превышения лимита запросов."""
    pass


class InvalidInputError(BotError):
    """Ошибка неверного входного запроса."""
    pass


def handle_error(error: Exception, context: Optional[dict] = None) -> BotResponse:
    """
    Обработать ошибку и вернуть структурированный ответ.
    
    Args:
        error: Исключение
        context: Дополнительный контекст (для логирования)
        
    Returns:
        BotResponse с сообщением об ошибке
    """
    user_id = context.get("user_id") if context else None
    logger.error(f"Bot error: {error}", exc_info=True, extra={"user_id": user_id})
    
    # Сообщения об ошибках
    error_messages = {
        'APITimeoutError': 'Сервис временно недоступен. Попробуйте позже.',
        'RateLimitError': 'Слишком много запросов. Подождите немного.',
        'InvalidInputError': 'Не удалось обработать запрос. Попробуйте переформулировать.',
        'DEFAULT': 'Произошла ошибка. Попробуйте позже или обратитесь в поддержку.'
    }
    
    # Определяем тип ошибки
    error_type = error.__class__.__name__
    if error_type in error_messages:
        message = error_messages[error_type]
    else:
        message = error_messages['DEFAULT']
    
    # Возвращаем BotResponse с флагами системного сообщения и ошибки
    return BotResponse(
        text=message,
        has_useful_content=False,
        is_system_message=True,
        is_error=True,
        topic='general'
    )
