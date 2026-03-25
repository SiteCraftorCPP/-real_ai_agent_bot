"""Оркестратор для контроля качества ответов LLM (v1.3.5)."""
import re
import logging
from typing import Optional
from datetime import datetime, timedelta
from bot.config import Config
from bot.database import load_user_escalation_data, save_user_escalation_data, increment_user_escalation

logger = logging.getLogger(__name__)

# Паттерны поясняющих фраз (дисклеймеров)
DISCLAIMER_PATTERNS = [
    r"(?:Это\s+)?справочная информация[^.]*\.",
    r"Данные носят ориентировочный характер[^.]*\.",
    r"Информация носит справочный характер[^.]*\.",
    r"не является юридической или налоговой консультацией[^.]*\.",
    r"в конкретной ситуации детали могут отличаться[^.]*\.",
    r"не заменяет индивидуальный анализ[^.]*\.",
    r"Оценка носит ориентировочный характер[^.]*\.",
    r"Дисклеймер:[^.]*\.",
]

# v1.3.4: Контролируемые дисклеймеры
# 'pricing' — обязательный при числовой оценке
# 'legal' — точечный при юридических рисках
# 'none' — информационные ответы без дисклеймера
DISCLAIMERS = {
    'pricing': 'Оценка носит ориентировочный характер и может отличаться от итоговой цены сделки.',
    'legal': 'В конкретной ситуации детали могут отличаться — важно проверить документы индивидуально.',
    'tax': 'В конкретной ситуации детали могут отличаться — важно проверить документы индивидуально.',
    'analytics': 'Данные носят ориентировочный характер и не заменяют индивидуальный анализ объекта.',
    'general': '',  # v1.3.4: убран универсальный дисклеймер для информационных ответов
}

# v1.3.4: Фраза о специалисте для добавления после оценки
SPECIALIST_SUGGESTION_AFTER_ESTIMATE = 'Для более точного анализа можно подключить специалиста компании.'

# v1.3.4: Паттерны для обнаружения числовой оценки в ответе LLM
NUMERIC_ESTIMATE_PATTERNS = [
    r"\d[\d\s]*(?:₽|руб|рублей|р\.)",  # "15 000 000 ₽" или "15000 руб"
    r"\d[\d\s]*(?:млн|миллион)",  # "15 млн"
    r"\d[\d\s]*(?:тыс|тысяч)",  # "500 тыс"
    r"\d[\d\s]*₽\s*/\s*м²",  # "220 000 ₽/м²"
    r"\d[\d\s]*(?:руб|₽)\s*/\s*(?:м²|кв\.?\s*м)",  # "руб/м²"
    r"(?:от|до|~|≈|около)\s*\d[\d\s]*(?:₽|руб|млн|тыс)",  # "от 10 млн" / "~15 млн"
    r"\d[\d\s]*[–—-]\s*\d[\d\s]*(?:₽|руб|млн|тыс)",  # "10–15 млн"
]

# Паттерны эскалации к специалисту
ESCALATION_PATTERNS = [
    r"(?:могу\s+)?передать\s+(?:ваш\s+)?запрос\s+(?:профильному\s+)?специалисту",
    r"подключить\s+специалиста",
    r"связаться\s+со\s+специалистом",
    r"обратиться\s+к\s+специалисту",
    r"помощь\s+специалиста",
    r"консультация\s+специалиста",
    r"передать\s+команде",
]

# Паттерны для определения предложения консультации в ответе LLM
CONSULTATION_OFFER_PATTERNS = [
    r"помогу\s+передать\s+запрос\s+специалисту",
    r"передам\s+заявку\s+команде",
    r"передам\s+запрос\s+команде",
    r"передать\s+запрос\s+специалисту\s+компании",
    r"передать\s+заявку\s+специалисту",
    r"передать\s+запрос\s+команде",
    r"передам\s+ваш\s+запрос",
    r"передам\s+заявку",
]

# Запрещённые обещания (поиск по онлайн-базам)
FORBIDDEN_PROMISES = [
    (r"(?:найду|поищу|посмотрю|проверю)\s+(?:на|в|по)\s+(?:ЦИАН|Авито|Домклик|Яндекс\.?Недвижимость)", 
     "К сожалению, я не имею доступа к онлайн-базам объявлений."),
    (r"(?:данные|информация|объявления)\s+(?:с|из|на)\s+(?:ЦИАН|Авито|Домклик)",
     "Я не имею доступа к актуальным данным с площадок объявлений."),
    (r"актуальные\s+(?:объявления|предложения)\s+(?:на|в)\s+(?:рынке|базах)",
     "Я работаю со справочной информацией и не имею доступа к live-данным."),
    (r"(?:покажу|выведу|найду)\s+(?:вам\s+)?(?:объявления|варианты|объекты)",
     "Я могу дать ориентиры и рекомендации, но не имею доступа к базам объявлений."),
]

# v1.3.2: Паттерны запросов на вложения (фото/файлы)
ATTACHMENT_REQUEST_PATTERNS = [
    r"(?:пришлите|отправьте|загрузите|приложите|скиньте|покажите)\s+(?:фото|фотографи|картинк|изображени)",
    r"(?:пришлите|отправьте|загрузите|приложите|скиньте)\s+(?:файл|документ|скан|pdf)",
    r"(?:прикреп|прилож|вложи)\w*\s+(?:фото|файл|документ|скан)",
    r"можете?\s+(?:вы\s+)?(?:прислать|отправить|показать)\s+(?:фото|файл|документ)",
    r"отправил\w*\s+(?:фото|файл|документ|картинк)",
]

ATTACHMENT_BLOCK_MESSAGE = """Я не могу принимать файлы и фотографии. Пожалуйста, опишите нужную информацию текстом.

Если нужно передать документы или фото объекта, можно:
• Описать ключевые параметры словами
• Обратиться к специалисту компании для детального разбора"""

# v1.3.5: Паттерны галлюцинаций о передаче заявки (модель утверждает, что заявка отправлена, хотя кнопка не нажата)
HALLUCINATION_LEAD_PATTERNS = [
    r"заявка\s+(?:передана|отправлена|принята|отправлена)",
    r"(?:я\s+)?отправил\w*\s+(?:запрос|заявку)\s+(?:специалисту|команде)",
    r"(?:я\s+)?передал\w*\s+(?:запрос|заявку)\s+(?:специалисту|команде)",
    r"специалист\s+(?:получил|принял)\s+(?:запрос|заявку)",
    r"(?:запрос|заявка)\s+(?:уже\s+)?(?:передан|отправлен|принят)",
    r"действие\s+(?:выполнено|осуществлено)",
]

# Названия классифайдов для детекции инструкций
CLASSIFIEDS = ["ЦИАН", "CIAN", "Авито", "Avito", "Домклик", "Яндекс.Недвижимость", "Яндекс Недвижимость"]

# Сообщение-заглушка при обнаружении инструкций по классифайдам
CLASSIFIEDS_BLOCK_MESSAGE = """Я не имею доступа к онлайн-базам объявлений и не могу давать инструкции по их использованию.

Могу помочь иначе:
• Дать ориентиры по ценам в нужном районе
• Объяснить, на что обращать внимание при выборе
• Передать запрос специалисту компании для персонального подбора

Что из этого вам подойдёт?"""


def contains_numeric_estimate(text: str) -> bool:
    """
    v1.3.4: Проверить, содержит ли текст числовую оценку (цена, диапазон, руб/м²).
    
    Args:
        text: Текст ответа LLM
        
    Returns:
        True если найдена числовая оценка
    """
    for pattern in NUMERIC_ESTIMATE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.debug(f"Обнаружена числовая оценка: {pattern[:40]}...")
            return True
    return False


def remove_duplicate_disclaimers(text: str) -> str:
    """
    Удалить все поясняющие фразы из текста (для последующего добавления одной).
    
    Args:
        text: Исходный текст ответа
        
    Returns:
        Текст без поясняющих фраз
    """
    result = text
    
    for pattern in DISCLAIMER_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Убираем лишние пустые строки
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = result.strip()
    
    return result


def ensure_single_disclaimer(text: str, topic: str, add_disclaimer: bool = True) -> str:
    """
    Гарантировать не более одной поясняющей фразы в конце ответа.
    
    Args:
        text: Текст ответа (уже очищенный от дублей)
        topic: Тема ответа ('general', 'analytics', 'tax', 'legal')
        add_disclaimer: Нужно ли добавлять поясняющую фразу
        
    Returns:
        Текст с одной поясняющей фразой в конце (или без неё)
    """
    if not add_disclaimer:
        return text
    
    disclaimer = DISCLAIMERS.get(topic, DISCLAIMERS['general'])
    
    # Проверяем, нет ли уже такой фразы
    if disclaimer.lower() in text.lower():
        return text
    
    return f"{text}\n\n{disclaimer}"


def should_suggest_escalation(context: dict, user_id: Optional[int] = None) -> bool:
    """
    Проверить, можно ли предлагать эскалацию к специалисту.
    v1.3.2: Добавлен лимит 2 эскалации/день + cooldown 12 часов.
    
    Args:
        context: Контекст сессии с escalation_data
        user_id: Telegram user ID (для проверки дневного лимита)
        
    Returns:
        True если можно предлагать эскалацию
    """
    if not Config.ESCALATION_ENABLED:
        return False
    
    escalation_data = context.get("escalation_data", {})
    
    # Если пользователь отказался - не предлагаем
    if escalation_data.get("user_declined", False):
        return False
    
    message_count = escalation_data.get("message_count", 0)
    last_escalation_at = escalation_data.get("last_escalation_at", 0)
    
    # Проверяем минимальный интервал между эскалациями
    messages_since_last = message_count - last_escalation_at
    if messages_since_last < Config.ESCALATION_MIN_MESSAGES:
        return False
    
    # v1.3.2: Проверка дневного лимита и cooldown из БД
    if user_id:
        db_escalation = load_user_escalation_data(user_id)
        
        # Проверка дневного лимита (max 2 в день)
        today = datetime.now().strftime("%Y-%m-%d")
        if db_escalation["daily_reset_at"] == today:
            if db_escalation["daily_count"] >= Config.ESCALATION_MAX_PER_DAY:
                logger.info(f"User {user_id} reached daily escalation limit ({Config.ESCALATION_MAX_PER_DAY})")
                return False
        
        # Проверка cooldown (12 часов между эскалациями)
        if db_escalation["last_escalation_at"]:
            try:
                last_time = datetime.fromisoformat(db_escalation["last_escalation_at"])
                cooldown_delta = timedelta(hours=Config.ESCALATION_COOLDOWN_HOURS)
                if datetime.now() - last_time < cooldown_delta:
                    logger.info(f"User {user_id} in escalation cooldown (last: {last_time})")
                    return False
            except (ValueError, TypeError) as e:
                logger.warning(f"Error parsing last_escalation_at: {e}")
    
    return True


def remove_escalation_if_not_allowed(text: str, context: dict, user_id: Optional[int] = None) -> tuple[str, bool]:
    """
    Удалить предложения эскалации из текста, если они не разрешены.
    v1.3.2: Учитывает дневной лимит и cooldown из БД.
    
    ВАЖНО: Паттерны эскалации специально составлены так, чтобы НЕ совпадать с 
    отдельными словами "специалист", "консультация", "передать запрос".
    Они удаляют только ПОЛНЫЕ ФРАЗЫ эскалации (например, "могу передать запрос специалисту").
    Упоминания специалистов в других контекстах остаются нетронутыми.
    
    Args:
        text: Текст ответа LLM
        context: Контекст сессии
        user_id: Telegram user ID (для проверки лимитов)
        
    Returns:
        (очищенный_текст, была_ли_эскалация_в_тексте)
    """
    had_escalation = False
    result = text
    
    # Проверяем наличие эскалации в тексте
    for pattern in ESCALATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            had_escalation = True
            break
    
    if not had_escalation:
        return text, False
    
    # Если эскалация не разрешена - удаляем ТОЛЬКО предложения с эскалацией
    if not should_suggest_escalation(context, user_id):
        for pattern in ESCALATION_PATTERNS:
            # v1.3.2: Улучшенная логика удаления - ищем границы предложения
            # Удаляем от начала предложения (после точки/начала текста) до конца (точка/конец)
            # Но НЕ удаляем отдельные слова "специалист" и т.д. - паттерны их не совпадают
            
            # Находим все совпадения
            matches = list(re.finditer(pattern, result, re.IGNORECASE))
            if not matches:
                continue
            
            # Удаляем каждое совпадение с контекстом предложения
            for match in reversed(matches):  # В обратном порядке, чтобы не сбивать индексы
                start = match.start()
                end = match.end()
                
                # Ищем начало предложения (последняя точка или начало текста перед match)
                sentence_start = result.rfind('.', 0, start)
                if sentence_start == -1:
                    sentence_start = result.rfind('\n', 0, start)
                sentence_start = sentence_start + 1 if sentence_start != -1 else 0
                
                # Ищем конец предложения (первая точка или конец текста после match)
                sentence_end = result.find('.', end)
                if sentence_end == -1:
                    sentence_end = result.find('\n', end)
                sentence_end = sentence_end + 1 if sentence_end != -1 else len(result)
                
                # Удаляем предложение целиком
                result = result[:sentence_start] + result[sentence_end:]
        
        # Убираем лишние пустые строки и пробелы
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r'\s{2,}', ' ', result)  # Двойные пробелы -> одинарные
        result = result.strip()
        
        logger.info(f"Эскалация удалена из ответа (не разрешена по правилам). User: {user_id if user_id else 'unknown'}")
        return result, True
    
    return text, True


def filter_forbidden_promises(text: str) -> str:
    """
    Заменить запрещённые обещания (поиск по онлайн-базам) на корректные формулировки.
    
    Args:
        text: Текст ответа LLM
        
    Returns:
        Отфильтрованный текст
    """
    result = text
    
    for pattern, replacement in FORBIDDEN_PROMISES:
        if re.search(pattern, result, re.IGNORECASE):
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            logger.info(f"Запрещённое обещание заменено: {pattern[:30]}...")
    
    return result


def filter_hallucinated_lead_confirmation(text: str) -> str:
    """
    v1.3.5: Заменить галлюцинации о «заявка передана/отправлена» на разрешённую фразу.
    Модель не должна утверждать, что заявка отправлена, если кнопка не нажата.
    """
    from bot.texts import SPECIALIST_ALLOWED_RESPONSE
    result = text
    for pattern in HALLUCINATION_LEAD_PATTERNS:
        if re.search(pattern, result, re.IGNORECASE):
            # Заменяем совпадающее предложение на разрешённую фразу (без дублирования)
            result = re.sub(
                r'[^.]*' + pattern + r'[^.]*\.?',
                SPECIALIST_ALLOWED_RESPONSE,
                result,
                count=1,
                flags=re.IGNORECASE
            )
            logger.info(f"Галлюцинация о передаче заявки заменена на разрешённую фразу")
            break
    return result


def contains_attachment_request(text: str) -> bool:
    """
    v1.3.2: Проверить, содержит ли текст запрос на отправку вложений (фото/файлы).
    
    Args:
        text: Текст ответа LLM
        
    Returns:
        True если найден запрос на вложения
    """
    for pattern in ATTACHMENT_REQUEST_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.info(f"Обнаружен запрос на вложения: {pattern[:40]}...")
            return True
    return False


def detect_consultation_offer(response_text: str) -> bool:
    """
    Определить, предлагает ли LLM консультацию специалиста в ответе.
    
    Args:
        response_text: Текст ответа от LLM
        
    Returns:
        True если в ответе есть предложение консультации
    """
    text_lower = response_text.lower()
    
    for pattern in CONSULTATION_OFFER_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.debug(f"Обнаружено предложение консультации: {pattern[:40]}...")
            return True
    
    return False


def contains_classifieds_instructions(text: str) -> bool:
    """
    Проверить, содержит ли текст инструкции по использованию классифайдов.
    Строгая проверка: название классифайда должно быть В КОНТЕКСТЕ инструкции.
    
    Args:
        text: Текст ответа LLM
        
    Returns:
        True если найдены инструкции по классифайдам
    """
    # Логируем для отладки (первые 200 символов)
    logger.debug(f"Проверка на инструкции классифайдов: {text[:200]}...")
    
    # Паттерны, где название классифайда РЯДОМ с инструкцией (в пределах 100 символов)
    # Это строгие паттерны - классифайд + действие в одном контексте
    strict_patterns = [
        # "на ЦИАН выберите / зайдите на Авито / откройте Домклик"
        r"(?:на|в|зайдите на|откройте|перейдите на)\s+(?:ЦИАН|CIAN|Авито|Avito|Домклик|Яндекс\.?Недвижимость)",
        # "в ЦИАН в разделе / на Авито в фильтрах"
        r"(?:ЦИАН|CIAN|Авито|Avito|Домклик|Яндекс\.?Недвижимость).{0,50}(?:в\s+разделе|в\s+фильтр|настрой|выбери|укажи|задай)",
        # "фильтры на ЦИАН / поиск на Авито"
        r"(?:фильтр|поиск|объявлени|уведомлени).{0,30}(?:на|в)\s+(?:ЦИАН|CIAN|Авито|Avito|Домклик)",
        # "сохраните поиск на ЦИАН"
        r"сохрани.{0,20}поиск.{0,30}(?:ЦИАН|CIAN|Авито|Avito|Домклик)",
        # "как искать на ЦИАН / инструкция по Авито"
        r"(?:как|инструкци).{0,20}(?:искать|найти|пользоваться).{0,30}(?:ЦИАН|CIAN|Авито|Avito|Домклик)",
    ]
    
    for pattern in strict_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logger.info(f"Обнаружены инструкции по классифайдам (строгий паттерн): {pattern[:40]}...")
            return True
    
    # Дополнительная проверка: ОЧЕНЬ длинный текст (>1000) с классифайдом И множеством инструкционных слов
    text_lower = text.lower()
    has_classified = any(c.lower() in text_lower for c in CLASSIFIEDS)
    
    if len(text) > 1000 and has_classified:
        # Считаем специфичные инструкционные слова для площадок
        platform_instruction_words = [
            "фильтр", "сортиров", "уведомлен", "подписк", "сохрани поиск",
            "тип объявлен", "цен диапазон", "район метро"
        ]
        matches = sum(1 for w in platform_instruction_words if w in text_lower)
        if matches >= 4:
            logger.info(f"Длинный текст ({len(text)} симв.) с классифайдом и {matches} специфичными словами - блокируем")
            return True
    
    return False


# v1.3.3: Паттерны для определения причин эскалации
RISKS_PATTERNS = [
    r"риск", r"опасн", r"проблем", r"негативн", r"плох",
    r"мошенничеств", r"обман", r"подвох"
]

DOCS_PATTERNS = [
    r"договор", r"контракт", r"документ", r"справк", r"выписк",
    r"егрн", r"кадастр", r"нотариус", r"регистрац"
]

COMPARISON_PATTERNS = [
    r"что\s+лучше", r"сравн", r"выбор", r"вариант",
    r"какой\s+выбрать", r"разниц", r"отличи"
]

LARGE_BUDGET_PATTERNS = [
    r"крупн\w+\s+бюджет", r"больш\w+\s+бюджет",
    r"бюджет\s*[>\>]\s*\d+\s*млн", r"бюджет\s*[>\>]\s*\d+\s*миллион",
    r"\d+\s*млн\s*[и\s]*выше", r"от\s+\d+\s*млн"
]

# Порог для крупного бюджета (в рублях)
LARGE_BUDGET_THRESHOLD = 10_000_000  # 10 млн руб

# Паттерны для явных и косвенных запросов на консультацию специалиста (v1.3.4)
SPECIALIST_REQUEST_PATTERNS = [
    # Простые совпадения (приоритетные)
    r"нужен\s+консультант",
    r"нужен\s+специалист",
    r"нужен\s+человек",
    r"нужен\s+эксперт",
    r"мне\s+нужен\s+(?:консультант|специалист|человек|эксперт)",
    # Варианты с "дай"
    r"дай\s+(?:мне\s+)?(?:консультант|специалист|человек|эксперт)",
    # Варианты с "хочу"
    r"хочу\s+(?:консультант|специалист|человек|эксперт)",
    r"хочу\s+поговорить\s+с\s+(?:консультант|специалист|эксперт|человек)",
    # Варианты с "подключи"
    r"подключи\s+(?:консультант|специалист|эксперт)",
    # v1.3.4: Косвенные запросы на специалиста
    r"кто\s+может\s+помочь",
    r"кому\s+обратиться",
    r"к\s+кому\s+обратиться",
    r"более\s+точн\w+\s+оценк",
    r"точн\w+\s+оценк",
    r"индивидуальн\w+\s+(?:консультаци|анализ|разбор)",
    r"(?:нужна|хочу|можно)\s+консультаци",
    r"(?:свяжите|соедините|подключите)\s+(?:меня\s+)?(?:с|со)\s+(?:специалист|консультант|эксперт)",
    r"(?:есть|можно)\s+(?:ли\s+)?(?:связаться|поговорить)\s+(?:с|со)\s+(?:специалист|консультант|эксперт|человек)",
    r"(?:помоги|помогите)\s+(?:связаться|найти)\s+(?:специалист|консультант|эксперт|человек)",
]


def detect_escalation_reason(user_text: str, context: dict) -> Optional[str]:
    """
    v1.3.3: Определить причину эскалации для классификации заявки.
    
    Args:
        user_text: Текст запроса пользователя
        context: Контекст сессии
        
    Returns:
        Причина эскалации: 'явный запрос', 'риски', 'документы', 'оценка', 'сравнение', 'крупный бюджет' или None
    """
    text_lower = user_text.lower().strip()
    
    # Проверка на явные запросы консультации (приоритетная проверка)
    # Сначала проверяем простые ключевые слова
    specialist_keywords = ["консультант", "специалист", "человек", "эксперт"]
    request_keywords = ["нужен", "нужна", "нужно", "хочу", "дай", "подключи", "свяжись", "соедини", "подключите", "свяжите"]
    
    # Проверка на наличие ключевых слов
    has_specialist = any(keyword in text_lower for keyword in specialist_keywords)
    has_request = any(keyword in text_lower for keyword in request_keywords)
    
    # Если есть оба типа ключевых слов - это явный запрос
    if has_specialist and has_request:
        logger.debug(f"Detected explicit specialist request: {user_text[:50]}")
        return "явный запрос"
    
    # Дополнительная проверка по паттернам
    for pattern in SPECIALIST_REQUEST_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.debug(f"Detected explicit specialist request via pattern: {pattern}")
            return "явный запрос"
    
    # Проверка на риски
    for pattern in RISKS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "риски"
    
    # Проверка на документы
    for pattern in DOCS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "документы"
    
    # Проверка на сравнение
    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "сравнение"
    
    # Проверка на крупный бюджет
    if is_large_budget(user_text, context):
        return "крупный бюджет"
    
    # Проверка на оценку (pricing)
    from bot.llm import PRICING_PATTERNS
    for pattern in PRICING_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "оценка"
    
    return None


def is_large_budget(user_text: str, context: dict) -> bool:
    """
    v1.3.3: Определить, является ли бюджет крупным (паттерны + числовой порог).
    
    Args:
        user_text: Текст запроса пользователя
        context: Контекст сессии (может содержать слоты с бюджетом)
        
    Returns:
        True если бюджет крупный
    """
    text_lower = user_text.lower()
    
    # Проверка паттернов
    for pattern in LARGE_BUDGET_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Проверка числового порога в тексте
    # Ищем суммы в формате: "X млн", "X миллионов", "X 000 000", "X000000"
    budget_patterns = [
        r"(\d+(?:\s*\d+)*)\s*млн",
        r"(\d+(?:\s*\d+)*)\s*миллион",
        r"(\d{1,3}(?:\s+\d{3})*)\s*000\s*000",  # "10 000 000"
        r"(\d{7,})",  # числа от 7 цифр (10 млн+)
    ]
    
    for pattern in budget_patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            try:
                # Извлекаем число
                num_str = match.group(1).replace(" ", "")
                amount = int(num_str)
                
                # Если это "млн" или "миллион", умножаем на 1_000_000
                if "млн" in match.group(0) or "миллион" in match.group(0):
                    amount *= 1_000_000
                elif len(num_str) < 7:  # Если число меньше 7 цифр, но есть "000 000", это уже миллионы
                    if "000" in match.group(0):
                        amount *= 1_000_000
                
                if amount >= LARGE_BUDGET_THRESHOLD:
                    return True
            except (ValueError, AttributeError):
                continue
    
    # Проверка слотов из контекста
    slots = context.get("slots", {})
    budget_slot = slots.get("budget")
    if budget_slot:
        # Пытаемся извлечь число из слота
        budget_text = str(budget_slot).lower()
        for pattern in budget_patterns:
            matches = re.finditer(pattern, budget_text, re.IGNORECASE)
            for match in matches:
                try:
                    num_str = match.group(1).replace(" ", "")
                    amount = int(num_str)
                    if "млн" in match.group(0) or "миллион" in match.group(0):
                        amount *= 1_000_000
                    if amount >= LARGE_BUDGET_THRESHOLD:
                        return True
                except (ValueError, AttributeError):
                    continue
    
    return False


def should_show_escalation_button(
    user_text: str,
    context: dict,
    user_id: Optional[int] = None
) -> tuple[bool, Optional[str]]:
    """
    v1.3.3: Определить, нужно ли показывать кнопку эскалации.
    
    Args:
        user_text: Текст запроса пользователя
        context: Контекст сессии
        user_id: Telegram user ID
    
    Returns:
        (should_show, reason) - нужно ли показывать кнопку и причина эскалации
    """
    if not Config.ESCALATION_ENABLED:
        return False, None
    
    escalation_data = context.get("escalation_data", {})
    
    # Если пользователь отказался - не показываем
    if escalation_data.get("user_declined", False):
        return False, None
    
    # Проверка условий эскалации
    reason = detect_escalation_reason(user_text, context)
    if not reason:
        return False, None
    
    # Для явных запросов на консультацию пропускаем проверки лимитов и cooldown
    is_explicit_request = (reason == "явный запрос")
    
    if not is_explicit_request:
        # Проверка лимитов (max 2/день, cooldown между отправками) - только для неявных запросов
        if not should_suggest_escalation(context, user_id):
            return False, None
        
        # Проверка cooldown между показами кнопки - только для неявных запросов
        message_count = escalation_data.get("message_count", 0)
        last_button_shown_at = escalation_data.get("last_button_shown_at", 0)
        messages_since_last_button = message_count - last_button_shown_at
        
        if messages_since_last_button < Config.ESCALATION_BUTTON_COOLDOWN_MESSAGES:
            logger.debug(f"User {user_id} button cooldown: {messages_since_last_button} < {Config.ESCALATION_BUTTON_COOLDOWN_MESSAGES}")
            return False, None
    
    return True, reason


def build_lead_message(
    user_id: int,
    username: Optional[str],
    user_text: str,
    context: dict,
    escalation_reason: Optional[str] = None
) -> str:
    """
    v1.3.3: Сформировать сообщение заявки для отправки в админ-чат.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username
        user_text: Последнее сообщение пользователя
        context: Контекст сессии
        escalation_reason: Причина эскалации (риски/документы/оценка/сравнение/крупный бюджет)
        
    Returns:
        Отформатированное сообщение заявки
    """
    from datetime import datetime
    
    # Дата и время
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Версия промпта
    prompt_version = "v1.3.4"
    
    # Формируем ссылку на пользователя
    if username and username != "N/A":
        user_link = f'<a href="tg://user?id={user_id}">@{username}</a>'
    else:
        user_link = f'<a href="tg://user?id={user_id}">{user_id}</a>'
    
    # Получаем слоты
    slots = context.get("slots", {})
    city = slots.get("city")
    goal = slots.get("goal")
    budget = slots.get("budget")
    object_type = slots.get("object_type")
    
    # Получаем последние сообщения из истории (5-10 сообщений)
    conversation_history = context.get("conversation_history", [])
    session_history = context.get("session_history", [])
    
    # Используем session_history если есть, иначе conversation_history
    recent_messages = session_history[-10:] if session_history else conversation_history[-10:]
    
    # Формируем контекст
    context_text = ""
    if recent_messages:
        context_text = "\n\nКонтекст (последние сообщения):\n"
        for msg in recent_messages[-10:]:  # Последние 10 сообщений
            role = "Пользователь" if msg.get("role") == "U" else "Бот"
            text = msg.get("text", "")[:200]  # Ограничиваем длину
            context_text += f"{role}: {text}\n"
    
    # Формируем сообщение
    message = (
        f"📩 Новая заявка на консультацию специалиста\n\n"
        f"Дата и время: {date_time}\n"
        f"Версия промпта: {prompt_version}\n"
        f"User: {user_link} (ID: {user_id})\n"
    )
    
    if escalation_reason:
        message += f"Причина эскалации: {escalation_reason}\n"
    
    message += f"\nПоследнее сообщение пользователя:\n{user_text}"
    
    # Добавляем слоты, если заполнены
    slots_parts = []
    if city:
        slots_parts.append(f"Город: {city}")
    if goal:
        slots_parts.append(f"Цель: {goal}")
    if budget:
        slots_parts.append(f"Бюджет: {budget}")
    if object_type:
        slots_parts.append(f"Тип объекта: {object_type}")
    
    if slots_parts:
        message += f"\n\nСлоты:\n" + "\n".join(slots_parts)
    
    # Добавляем контекст
    if context_text:
        message += context_text
    
    return message


def build_slots_summary(slots: dict) -> str:
    """
    Построить краткое резюме слотов для системного промпта.
    
    Args:
        slots: Словарь со слотами (city, budget, object_type, goal)
        
    Returns:
        Краткое резюме или пустая строка
    """
    if not slots or not any(slots.values()):
        return ""
    
    parts = []
    
    if slots.get("city"):
        parts.append(f"Город: {slots['city']}")
    if slots.get("object_type"):
        parts.append(f"Тип: {slots['object_type']}")
    if slots.get("goal"):
        parts.append(f"Цель: {slots['goal']}")
    if slots.get("budget"):
        parts.append(f"Бюджет: {slots['budget']}")
    
    if not parts:
        return ""
    
    return "Известно о пользователе: " + ", ".join(parts) + "."


def process_response(
    raw_response: str,
    context: dict,
    topic: str = 'general',
    is_system_message: bool = False,
    is_error: bool = False,
    user_id: Optional[int] = None,
    user_text: Optional[str] = None
) -> tuple[str, dict]:
    """
    Главная функция оркестратора - обработка ответа LLM.
    v1.3.4: Обязательная эскалация после числовой оценки, контролируемые дисклеймеры.
    
    Args:
        raw_response: Сырой ответ от LLM
        context: Контекст сессии
        topic: Тема ответа ('general', 'analytics', 'tax', 'legal')
        is_system_message: Это системное сообщение
        is_error: Это сообщение об ошибке
        user_id: Telegram user ID (для логирования и лимитов)
        user_text: Текст запроса пользователя (для определения эскалации)
        
    Returns:
        (обработанный_текст, обновлённый_контекст)
        В контексте добавлены поля: should_show_escalation_button, escalation_reason
    """
    # Логирование RAW ответа
    if user_id:
        logger.info(f"[RAW] User {user_id}: {raw_response[:200]}{'...' if len(raw_response) > 200 else ''}")
    
    # Для системных сообщений и ошибок - не обрабатываем
    if is_system_message or is_error:
        if user_id:
            logger.info(f"[FINAL] User {user_id}: {raw_response[:200]}{'...' if len(raw_response) > 200 else ''}")
        return raw_response, context
    
    result = raw_response
    updated_context = context.copy()
    
    # 0. Блокировка инструкций по классифайдам (полная замена ответа)
    if contains_classifieds_instructions(result):
        logger.warning("Ответ содержит инструкции по классифайдам - заменяем на заглушку")
        if user_id:
            logger.info(f"[FINAL] User {user_id}: {CLASSIFIEDS_BLOCK_MESSAGE[:200]}{'...' if len(CLASSIFIEDS_BLOCK_MESSAGE) > 200 else ''}")
        return CLASSIFIEDS_BLOCK_MESSAGE, updated_context
    
    # 0.1. Блокировка запросов на вложения (фото/файлы)
    if contains_attachment_request(result):
        logger.warning("Ответ содержит запрос на вложения - заменяем на заглушку")
        if user_id:
            logger.info(f"[FINAL] User {user_id}: {ATTACHMENT_BLOCK_MESSAGE[:200]}{'...' if len(ATTACHMENT_BLOCK_MESSAGE) > 200 else ''}")
        return ATTACHMENT_BLOCK_MESSAGE, updated_context
    
    # 1. Фильтрация запрещённых обещаний
    result = filter_forbidden_promises(result)
    
    # 1.1. v1.3.5: Фильтр галлюцинаций о передаче заявки (модель не должна утверждать, что заявка отправлена)
    result = filter_hallucinated_lead_confirmation(result)
    
    # 2. Удаление дублей поясняющих фраз
    result = remove_duplicate_disclaimers(result)
    
    # 3. v1.3.4: Определение числовой оценки и контролируемые дисклеймеры
    has_numeric_estimate = contains_numeric_estimate(result)
    has_legal_risks = any(re.search(p, result, re.IGNORECASE) for p in RISKS_PATTERNS)
    
    # Определяем тип дисклеймера (pricing > legal > analytics > none)
    if has_numeric_estimate:
        disclaimer_type = 'pricing'
    elif has_legal_risks or topic in ('legal', 'tax'):
        disclaimer_type = 'legal'
    elif topic == 'analytics':
        disclaimer_type = 'analytics'
    else:
        disclaimer_type = 'general'  # v1.3.4: пустой дисклеймер для общих ответов
    
    # 4. Определение показа кнопки эскалации
    escalation_data = updated_context.get("escalation_data", {
        "message_count": 0,
        "last_escalation_at": 0,
        "last_button_shown_at": 0,
        "button_shown_count": 0,
        "user_declined": False
    })
    escalation_data["message_count"] = escalation_data.get("message_count", 0) + 1
    
    should_show_button = False
    escalation_reason = None
    
    # v1.3.4: При числовой оценке — принудительная кнопка эскалации
    if has_numeric_estimate:
        should_show_button = True
        escalation_reason = "pricing"
        logger.info(f"Forced escalation button for numeric estimate (user {user_id})")
    
    if user_text and not should_show_button:
        should_show_button, escalation_reason = should_show_escalation_button(
            user_text, updated_context, user_id
        )
    
    if should_show_button:
        # Фиксируем показ кнопки
        escalation_data["last_button_shown_at"] = escalation_data["message_count"]
        escalation_data["button_shown_count"] = escalation_data.get("button_shown_count", 0) + 1
        logger.info(f"Escalation button shown to user {user_id}, reason: {escalation_reason}")
    
    updated_context["escalation_data"] = escalation_data
    updated_context["should_show_escalation_button"] = should_show_button
    updated_context["escalation_reason"] = escalation_reason
    
    # 5. v1.3.4: Контролируемые дисклеймеры
    # Добавляем дисклеймер только если он непустой (для pricing/legal/analytics)
    disclaimer_text = DISCLAIMERS.get(disclaimer_type, '')
    if disclaimer_text:
        result = ensure_single_disclaimer(result, disclaimer_type, add_disclaimer=True)
    
    # 5.1. v1.3.4: Если числовая оценка — добавляем фразу о специалисте
    if has_numeric_estimate and SPECIALIST_SUGGESTION_AFTER_ESTIMATE.lower() not in result.lower():
        result = f"{result}\n\n{SPECIALIST_SUGGESTION_AFTER_ESTIMATE}"
    
    # Логирование FINAL ответа
    if user_id:
        logger.info(f"[FINAL] User {user_id}: {result[:200]}{'...' if len(result) > 200 else ''}")
    
    return result, updated_context


def mark_escalation_declined(context: dict) -> dict:
    """
    Отметить, что пользователь отказался от эскалации.
    
    Args:
        context: Контекст сессии
        
    Returns:
        Обновлённый контекст
    """
    updated_context = context.copy()
    escalation_data = updated_context.get("escalation_data", {})
    escalation_data["user_declined"] = True
    updated_context["escalation_data"] = escalation_data
    return updated_context


def reset_escalation_declined(context: dict) -> dict:
    """
    Сбросить флаг отказа от эскалации (например, в новой сессии).
    
    Args:
        context: Контекст сессии
        
    Returns:
        Обновлённый контекст
    """
    updated_context = context.copy()
    escalation_data = updated_context.get("escalation_data", {})
    escalation_data["user_declined"] = False
    updated_context["escalation_data"] = escalation_data
    return updated_context
