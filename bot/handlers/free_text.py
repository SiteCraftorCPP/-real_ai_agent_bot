"""Handler for free text input (not commands or menu buttons)."""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from bot.texts import (
    MENU_RENT,
    MENU_BUY_SELL,
    MENU_ANALYTICS,
    MENU_DOCS_TAXES,
    MENU_ABOUT_SPECIALIST,
    FEEDBACK_THANKS_DOWN_FINAL,
)
from bot.state import MenuState, FeedbackState, SpecialistRequest
from bot.llm import generate_reply
from bot.orchestrator import detect_consultation_offer
from bot.keyboards import get_feedback_keyboard, get_escalation_button, get_consultation_request_keyboard
from bot.config import Config
from bot.context import (
    get_session_context,
    add_to_conversation_history,
    update_escalation_data,
    add_to_session_history,
    get_current_session_id,
    get_session_history_from_state,
    format_session_for_file,
)
from bot.database import get_session_info
from bot.errors import handle_error, APITimeoutError
from bot.utils import (
    is_docs_or_taxes_topic,
    BotResponse,
    send_long,
    add_history,
)
from bot.orchestrator import process_response, build_lead_message
from bot.database import increment_user_escalation
from bot.rate_limiter import check_rate_limit, record_message

logger = logging.getLogger(__name__)
router = Router()

# Keywords that indicate need for specialist (for adding suggestion after answer)
SPECIALIST_KEYWORDS = [
    "оцен",
    "за сколько",
    "бюджет",
    "что лучше",
    "ипотек",
    "налог",
    "документ",
]


async def _safe_callback_answer(
    callback: CallbackQuery | None,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    """Safely answer callback query (ignore stale/already-answered errors)."""
    if not callback:
        return
    try:
        await callback.answer(text or "", show_alert=show_alert)
    except Exception as e:
        logger.debug(f"Skip callback.answer due to Telegram error: {e}")

@router.message(
    F.text,
    ~F.text.startswith("/"),  # Exclude commands
    ~F.text.in_([MENU_RENT, MENU_BUY_SELL, MENU_ANALYTICS, MENU_DOCS_TAXES, MENU_ABOUT_SPECIALIST]),  # Exclude menu buttons
    F.chat.id > 0  # v1.3.3: Только для личных чатов (группы обрабатываются отдельным обработчиком)
)
async def handle_free_text(message: Message, state: FSMContext) -> None:
    """Handle free text input: check feedback state, generate LLM reply with disclaimers."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    text = message.text
    logger.info(f"User {user_id} (@{username}) sent text: {text}")
    
    # Ignore messages from feedback chat - bot should not respond there
    if Config.FEEDBACK_CHAT_ID != 0 and message.chat.id == Config.FEEDBACK_CHAT_ID:
        logger.info(f"Ignoring message from feedback chat {Config.FEEDBACK_CHAT_ID}")
        return
    
    # Check current state
    current_state = await state.get_state()
    
    # If user is in specialist consultation flow, let specialist.py handle it
    if current_state and current_state.startswith("SpecialistRequest"):
        return
    
    # Check if user is in feedback comment state (v1.1: awaiting_other_comment)
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        # This is handled in feedback.py, but keep for backward compatibility
        # The new flow uses awaiting_other_comment
        return
    
    # v1.3.2: Check rate limits BEFORE processing
    rate_limit_result = check_rate_limit(user_id)
    if not rate_limit_result.allowed:
        logger.warning(f"User {user_id} rate limited: {rate_limit_result.message}")
        await message.answer(rate_limit_result.message)
        return
    
    # Add to history
    add_history(user_id, "U", text)
    
    # v1.3.2: Record message for rate limiting
    record_message(user_id)
    
    # Regular question handling - ALWAYS call LLM first (v1.1 principle)
    # Получаем контекст сессии (v1.3.2: передаем user_id для загрузки слотов)
    context = await get_session_context(state, user_id)
    selected_section = context.get("selected_section")
    
    # Добавляем сообщение в историю разговора (legacy)
    await add_to_conversation_history(state, "U", text)
    
    # Добавляем в историю сессии (state + DB)
    await add_to_session_history(state, "U", text)
    
    # Подготавливаем session_data для LLM: история после записи текущего сообщения,
    # чтобы в LLM ушло окно предыдущих реплик (user+assistant), без дубля текущего вопроса.
    collected_data = context.get("collected_data", {})
    fresh = await state.get_data()
    conv = fresh.get("conversation_history", [])
    history_before_current = conv[:-1] if conv and conv[-1].get("role") == "U" else conv
    sess = fresh.get("session_history", [])
    session_history_before_current = sess[:-1] if sess and sess[-1].get("role") == "U" else sess
    session_data = {
        "collected_data": collected_data,
        "asked_questions": context.get("asked_questions", []),
        "selected_section": selected_section,
        "conversation_history": history_before_current,
        "session_history": session_history_before_current,
    }
    
    # Также добавляем плоские поля для обратной совместимости
    if collected_data.get("location", {}).get("city"):
        session_data["city"] = collected_data["location"]["city"]
    if collected_data.get("object_type"):
        session_data["property_type"] = collected_data["object_type"]
    if collected_data.get("request_type"):
        session_data["request_type"] = collected_data["request_type"]
    if collected_data.get("budget"):
        session_data["budget"] = collected_data["budget"]
    if collected_data.get("urgency"):
        session_data["urgency"] = collected_data["urgency"]
    
    # v1.3.2: Send loading messages (changed emoji from 🤖 to 🤔)
    loading_msg1 = await message.answer("🤔")
    loading_msg2 = await message.answer("<i>Анализирую ваш вопрос и готовлю ответ…</i>", parse_mode="HTML")
    
    # Определяем topic для BotResponse
    if is_docs_or_taxes_topic(text, selected_section):
        topic = 'tax'
    elif selected_section == "market" or selected_section == "analytics":
        topic = 'analytics'
    else:
        topic = 'general'
    
    # Generate LLM reply
    bot_response = None
    try:
        reply_text = await generate_reply(text, selected_section, session_data if session_data else None)
        
        # Создаем BotResponse
        bot_response = BotResponse(
            text=reply_text,
            has_useful_content=True,
            is_system_message=False,
            is_error=False,
            topic=topic
        )
    except Exception as e:
        logger.error(f"Error generating reply: {e}", exc_info=True)
        # Обрабатываем ошибку через централизованный обработчик
        error_context = {"user_id": user_id}
        bot_response = handle_error(e, error_context)
    finally:
        # Delete loading messages
        try:
            await loading_msg1.delete()
            await loading_msg2.delete()
        except Exception as e:
            logger.warning(f"Failed to delete loading messages: {e}")
    
    # Обрабатываем ответ через оркестратор (v1.3.3: передаем user_id и user_text)
    should_show_escalation_button = False
    escalation_reason = None
    
    if Config.ORCHESTRATOR_ENABLED and bot_response.has_useful_content:
        final_text, updated_context = process_response(
            raw_response=bot_response.text,
            context=context,
            topic=topic,
            is_system_message=bot_response.is_system_message,
            is_error=bot_response.is_error,
            user_id=user_id,
            user_text=text
        )
        # Сохраняем обновлённые данные эскалации
        if "escalation_data" in updated_context:
            await update_escalation_data(state, updated_context["escalation_data"])
        
        # v1.3.3: Проверяем флаг показа кнопки эскалации
        should_show_escalation_button = updated_context.get("should_show_escalation_button", False)
        escalation_reason = updated_context.get("escalation_reason")
        
        if should_show_escalation_button:
            logger.info(f"Escalation button shown to user {user_id}, reason: {escalation_reason}")
    else:
        final_text = bot_response.text
    
    # Save data for feedback
    await state.update_data(
        last_question_text=text,
        last_answer_text=final_text,
        last_section=selected_section or "не выбран"
    )
    
    # Добавляем в историю разговора (legacy)
    await add_to_conversation_history(state, "B", final_text)
    
    # Добавляем в историю сессии (state + DB)
    await add_to_session_history(state, "B", final_text)
    
    # Add to legacy history (для обратной совместимости)
    add_history(user_id, "B", final_text)
    
    # Выбираем клавиатуру по приоритету:
    # 1. Кнопка эскалации (если should_show_escalation_button == True)
    # 2. Кнопка запроса консультации (если LLM предлагает консультацию)
    # 3. Кнопки фидбека (по умолчанию)
    if should_show_escalation_button:
        reply_markup = get_escalation_button()
    elif detect_consultation_offer(final_text):
        reply_markup = get_consultation_request_keyboard()
        logger.info(f"Consultation offer detected for user {user_id}, showing consultation request button")
    else:
        reply_markup = get_feedback_keyboard()
    
    # Send using send_long
    await send_long(message, final_text, reply_markup=reply_markup)


async def send_specialist_lead(
    bot,
    state: FSMContext,
    user_id: int,
    username: str | None,
    reason: str,
    reply_message=None,
    callback: CallbackQuery | None = None,
) -> None:
    """
    v1.3.4: Единый backend handler для формирования и отправки заявки специалисту.
    Используется кнопкой эскалации, меню и командой /specialist.
    
    Заявка содержит: user_id, timestamp, prompt_version=1.3.4, reason,
    последние 5-10 сообщений, слоты. Без доп. вопросов и подтверждений.
    
    Args:
        bot: Bot instance
        state: FSM context
        user_id: Telegram user ID
        username: Telegram username
        reason: Причина (pricing/risks/specialist_request/manual_menu_request)
        reply_message: Сообщение для ответа пользователю
        callback: CallbackQuery (опционально)
    """
    username = username or "N/A"
    
    # Проверка лимита (max 2/день)
    from bot.database import load_user_escalation_data
    db_escalation = load_user_escalation_data(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    # Отключение лимита: если ESCALATION_MAX_PER_DAY <= 0 — лимит не применяется.
    if (
        Config.ESCALATION_MAX_PER_DAY > 0
        and db_escalation["daily_reset_at"] == today
        and db_escalation["daily_count"] >= Config.ESCALATION_MAX_PER_DAY
    ):
        limit_text = "Вы уже отправили максимальное количество заявок на сегодня. Попробуйте завтра."
        if callback:
            await _safe_callback_answer(callback, limit_text, show_alert=True)
        elif reply_message:
            await reply_message.answer(limit_text)
        return
    
    # Получаем контекст сессии
    context = await get_session_context(state, user_id)
    
    # Получаем последнее сообщение пользователя
    data = await state.get_data()
    user_text = data.get("last_question_text", "Не указано")
    
    # Формируем заявку через единый build_lead_message
    lead_message = build_lead_message(
        user_id=user_id,
        username=username,
        user_text=user_text,
        context=context,
        escalation_reason=reason,
    )
    
    # Отправляем в админ-чат
    try:
        send_kwargs = {
            "chat_id": Config.FEEDBACK_CHAT_ID,
            "text": lead_message,
            "parse_mode": "HTML",
        }
        if Config.LEADS_TOPIC_ID != 0:
            send_kwargs["message_thread_id"] = Config.LEADS_TOPIC_ID
        
        await bot.send_message(**send_kwargs)
        logger.info(f"Lead sent to chat {Config.FEEDBACK_CHAT_ID}, topic {Config.LEADS_TOPIC_ID}, user {user_id}, reason={reason}")
        
        # Отправляем файл с историей переписки
        section = data.get("last_section") or data.get("selected_section")
        await send_manager_request_with_history(
            bot=bot,
            state=state,
            user_id=user_id,
            username=username if username != "N/A" else None,
            chat_id=Config.FEEDBACK_CHAT_ID,
            topic_id=Config.LEADS_TOPIC_ID,
            section=section,
        )
        
        # Фиксируем отправку заявки в БД
        increment_user_escalation(user_id)
        
        # Обновляем escalation_data в контексте
        escalation_data = context.get("escalation_data", {})
        escalation_data["last_escalation_at"] = escalation_data.get("message_count", 0)
        await update_escalation_data(state, escalation_data)
        
        # Подтверждение пользователю — без доп. вопросов
        confirmation_text = "Заявка принята. Специалист свяжется с вами."
        if callback:
            await _safe_callback_answer(callback, confirmation_text, show_alert=False)
        if reply_message:
            await reply_message.answer(confirmation_text)
        
    except Exception as e:
        logger.error(f"Failed to send lead: {e}", exc_info=True)
        error_text = "Произошла ошибка при отправке заявки. Попробуйте позже."
        if callback:
            await _safe_callback_answer(callback, error_text, show_alert=True)
        elif reply_message:
            await reply_message.answer(error_text)


async def send_manager_request_with_history(
    bot,
    state: FSMContext,
    user_id: int,
    username: str | None,
    chat_id: int,
    topic_id: int = 0,
    section: str | None = None
) -> None:
    """
    Send session history as .txt file to manager chat.
    
    Args:
        bot: Bot instance
        state: FSM context
        user_id: Telegram user ID
        username: Telegram username
        chat_id: Target chat ID
        topic_id: Optional topic ID for supergroup
        section: Section name (optional)
    """
    try:
        # Get session history
        session_id = await get_current_session_id(state)
        session_history = await get_session_history_from_state(state)
        
        if not session_history:
            logger.info(f"No session history found for user {user_id}")
            return
        
        # Get session info
        data = await state.get_data()
        session_info = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "section": section or data.get("session_section") or data.get("last_section") or "не выбран",
            "started_at": datetime.now().isoformat()  # Fallback
        }
        
        # Try to get from DB
        if session_id:
            db_info = get_session_info(session_id)
            if db_info:
                session_info.update(db_info)
        
        # Format and send file
        file_content = format_session_for_file(
            session_info=session_info,
            messages=session_history,
            reason=None,
            comment=None
        )
        
        # Create file
        file_bytes = file_content.encode("utf-8")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{user_id}_{timestamp}.txt"
        
        file = BufferedInputFile(file_bytes, filename=filename)
        
        send_doc_kwargs = {
            "chat_id": chat_id,
            "document": file,
            "caption": f"📎 История сессии для user {user_id}"
        }
        # Добавляем message_thread_id если тема задана
        if topic_id != 0:
            send_doc_kwargs["message_thread_id"] = topic_id
        
        await bot.send_document(**send_doc_kwargs)
        logger.info(f"Session history file sent to chat {chat_id}, topic {topic_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send session history file: {e}", exc_info=True)


@router.callback_query(F.data == "escalation:confirm")
async def handle_escalation_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """
    v1.3.4: Обработчик нажатия кнопки эскалации — делегирует в send_specialist_lead.
    """
    user_id = callback.from_user.id
    username = callback.from_user.username
    
    logger.info(f"Escalation button clicked by user {user_id}")
    # Быстрый ACK, чтобы Telegram сразу закрыл "часики" на кнопке.
    await _safe_callback_answer(callback, "Отправляю заявку специалисту…")
    
    # Получаем причину из контекста (pricing/risks/...)
    context = await get_session_context(state, user_id)
    escalation_reason = context.get("escalation_reason") or "specialist_request"
    
    await send_specialist_lead(
        bot=callback.message.bot,
        state=state,
        user_id=user_id,
        username=username,
        reason=escalation_reason,
        reply_message=callback.message,
        callback=callback,
    )


@router.callback_query(F.data == "consultation:request")
async def handle_consultation_request(callback: CallbackQuery, state: FSMContext) -> None:
    """
    v1.3.4: Обработчик кнопки запроса консультации — делегирует в send_specialist_lead.
    """
    user_id = callback.from_user.id
    username = callback.from_user.username
    
    logger.info(f"Consultation request button clicked by user {user_id}")
    # Быстрый ACK, чтобы Telegram сразу закрыл "часики" на кнопке.
    await _safe_callback_answer(callback, "Отправляю заявку специалисту…")
    
    await send_specialist_lead(
        bot=callback.message.bot,
        state=state,
        user_id=user_id,
        username=username,
        reason="specialist_request",
        reply_message=callback.message,
        callback=callback,
    )
