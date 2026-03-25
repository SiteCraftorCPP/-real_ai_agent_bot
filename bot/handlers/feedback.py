"""Handler for feedback callbacks."""
import io
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from bot.texts import (
    FEEDBACK_THANKS_UP,
    FEEDBACK_DOWN_PICK,
    FEEDBACK_DOWN_THANKS,
    FEEDBACK_DOWN_ASK_OTHER,
)
from bot.state import FeedbackState, MenuState
from bot.keyboards import get_feedback_reasons_kb
from bot.utils import get_last_history
from bot.config import Config
from bot.database import save_feedback, get_session_info
from bot.context import (
    get_current_session_id,
    get_session_history_from_state,
    format_session_for_file,
)

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "fb:up")
async def handle_feedback_up(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle positive feedback (👍)."""
    user_id = callback.from_user.id
    username = callback.from_user.username
    logger.info(f"User {user_id} gave positive feedback")
    
    # Get context for saving
    data = await state.get_data()
    
    last_question = data.get("last_question_text", "")
    last_answer = data.get("last_answer_text", "")
    last_section = data.get("last_section", "")
    
    # Save to database
    save_feedback(
        user_id=user_id,
        username=username,
        rating="positive",
        question=last_question,
        answer=last_answer,
        section=last_section
    )
    
    # Send to feedback chat if configured
    if Config.FEEDBACK_CHAT_ID != 0:
        # Format with clickable user ID
        username_str = f"@{username}" if username else "N/A"
        feedback_message = (
            f"👍 Positive Feedback\n\n"
            f"User:\n"
            f"• <a href=\"tg://user?id={user_id}\">{user_id}</a>\n"
            f"• {username_str}\n"
            f"Section: {last_section}\n\n"
            f"Q: {last_question}\n"
            f"A: {last_answer[:500]}{'...' if len(last_answer) > 500 else ''}"
        )
        try:
            send_kwargs = {
                "chat_id": Config.FEEDBACK_CHAT_ID,
                "text": feedback_message,
                "parse_mode": "HTML"
            }
            # Добавляем message_thread_id если тема задана
            if Config.FEEDBACK_TOPIC_ID != 0:
                send_kwargs["message_thread_id"] = Config.FEEDBACK_TOPIC_ID
            
            await callback.message.bot.send_message(**send_kwargs)
            logger.info(f"Positive feedback sent to chat {Config.FEEDBACK_CHAT_ID}, topic {Config.FEEDBACK_TOPIC_ID}")
        except Exception as e:
            logger.error(f"Failed to send positive feedback: {e}")
    
    await callback.answer()
    await callback.message.answer(FEEDBACK_THANKS_UP)


@router.callback_query(F.data == "fb:down")
async def handle_feedback_down(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle negative feedback (👎) - show reason selection."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} gave negative feedback")
    
    await callback.answer()
    await callback.message.answer(
        FEEDBACK_DOWN_PICK,
        reply_markup=get_feedback_reasons_kb()
    )


@router.callback_query(F.data.startswith("fb:reason:"))
async def handle_feedback_reason(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle feedback reason selection."""
    user_id = callback.from_user.id
    username = callback.from_user.username
    reason_data = callback.data
    
    # Map reason codes to readable names
    reason_map = {
        "fb:reason:facts": "❌ ошибка фактов",
        "fb:reason:unclear": "🤷 непонятно",
        "fb:reason:risky": "⚠️ опасный / сомнительный совет",
        "fb:reason:other": "📝 другое",
    }
    reason_name = reason_map.get(reason_data, reason_data)
    
    logger.info(f"User {user_id} selected feedback reason: {reason_name}")
    
    await callback.answer()
    
    # Get data from state
    data = await state.get_data()
    last_question = data.get("last_question_text", "")
    last_answer = data.get("last_answer_text", "")
    last_section = data.get("last_section", "")
    
    # Save reason
    await state.update_data(last_feedback_reason=reason_name)
    
    # If "other" - ask for comment (feedback will be sent after comment)
    if reason_data == "fb:reason:other":
        await callback.message.answer(FEEDBACK_DOWN_ASK_OTHER)
        await state.set_state(FeedbackState.awaiting_other_comment)
    else:
        # Send to feedback chat if configured
        if Config.FEEDBACK_CHAT_ID != 0:
            await send_feedback_with_history(
                bot=callback.message.bot,
                state=state,
                user_id=user_id,
                username=username,
                reason=reason_name,
                last_question=last_question,
                last_answer=last_answer,
                last_section=last_section
            )
        
        # Save to database (without comment)
        save_feedback(
            user_id=user_id,
            username=username,
            rating="negative",
            reason=reason_name,
            question=last_question,
            answer=last_answer,
            section=last_section
        )
        # Just thank and finish
        await callback.message.answer(FEEDBACK_DOWN_THANKS)
        # Don't clear state, preserve selected_section


@router.message(FeedbackState.awaiting_other_comment)
async def handle_feedback_other_comment(message: Message, state: FSMContext) -> None:
    """Handle comment for 'other' feedback reason."""
    user_id = message.from_user.id
    username = message.from_user.username
    comment = message.text
    logger.info(f"User {user_id} provided feedback comment: {comment}")
    
    # Get data
    data = await state.get_data()
    reason = data.get("last_feedback_reason", "📝 другое")
    selected_section = data.get("selected_section")
    last_question = data.get("last_question_text", "")
    last_answer = data.get("last_answer_text", "")
    last_section = data.get("last_section", "")
    
    # Save to database (with comment)
    save_feedback(
        user_id=user_id,
        username=username,
        rating="negative",
        reason=reason,
        comment=comment,
        question=last_question,
        answer=last_answer,
        section=last_section
    )
    
    # Send to feedback chat if configured
    if Config.FEEDBACK_CHAT_ID != 0:
        await send_feedback_with_history(
            bot=message.bot,
            state=state,
            user_id=user_id,
            username=username,
            reason=reason,
            comment=comment,
            last_question=last_question,
            last_answer=last_answer,
            last_section=last_section
        )
    
    # Thank user
    await message.answer(FEEDBACK_DOWN_THANKS)
    
    # Clear feedback state but preserve selected_section and session data
    current_session_id = data.get("current_session_id")
    session_history = data.get("session_history", [])
    
    await state.clear()
    if selected_section:
        await state.set_state(MenuState.selected_section)
        await state.update_data(
            selected_section=selected_section,
            current_session_id=current_session_id,
            session_history=session_history
        )


async def send_feedback_with_history(
    bot,
    state: FSMContext,
    user_id: int,
    username: str | None,
    reason: str,
    last_question: str,
    last_answer: str,
    last_section: str,
    comment: str | None = None
) -> None:
    """
    Send feedback message to feedback chat with session history as .txt file.
    
    Args:
        bot: Bot instance
        state: FSM context
        user_id: Telegram user ID
        username: Telegram username
        reason: Feedback reason
        last_question: Last question text
        last_answer: Last answer text  
        last_section: Section name
        comment: Optional comment text
    """
    # Format with clickable user ID
    username_str = f"@{username}" if username else "N/A"
    
    feedback_message = (
        f"👎 Negative Feedback\n\n"
        f"Reason: {reason}\n"
    )
    
    if comment:
        feedback_message += f"Comment: {comment}\n"
    
    feedback_message += (
        f"\nUser:\n"
        f"• <a href=\"tg://user?id={user_id}\">{user_id}</a>\n"
        f"• {username_str}\n"
        f"Section: {last_section}\n\n"
        f"Q: {last_question}\n"
        f"A: {last_answer[:500]}{'...' if len(last_answer) > 500 else ''}"
    )
    
    try:
        # Send main message
        send_kwargs = {
            "chat_id": Config.FEEDBACK_CHAT_ID,
            "text": feedback_message,
            "parse_mode": "HTML"
        }
        # Добавляем message_thread_id если тема задана
        if Config.FEEDBACK_TOPIC_ID != 0:
            send_kwargs["message_thread_id"] = Config.FEEDBACK_TOPIC_ID
        
        await bot.send_message(**send_kwargs)
        
        # Get session history and send as file
        session_id = await get_current_session_id(state)
        session_history = await get_session_history_from_state(state)
        
        if session_history:
            # Get session info
            data = await state.get_data()
            session_info = {
                "session_id": session_id,
                "user_id": user_id,
                "username": username,
                "section": data.get("session_section", last_section),
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
                reason=reason,
                comment=comment
            )
            
            # Create file
            file_bytes = file_content.encode("utf-8")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{user_id}_{timestamp}.txt"
            
            file = BufferedInputFile(file_bytes, filename=filename)
            
            send_doc_kwargs = {
                "chat_id": Config.FEEDBACK_CHAT_ID,
                "document": file,
                "caption": f"📎 История сессии для user {user_id}"
            }
            # Добавляем message_thread_id если тема задана
            if Config.FEEDBACK_TOPIC_ID != 0:
                send_doc_kwargs["message_thread_id"] = Config.FEEDBACK_TOPIC_ID
            
            await bot.send_document(**send_doc_kwargs)
            
        logger.info(f"Feedback sent to chat {Config.FEEDBACK_CHAT_ID}, topic {Config.FEEDBACK_TOPIC_ID}")
    except Exception as e:
        logger.error(f"Failed to send feedback: {e}")
