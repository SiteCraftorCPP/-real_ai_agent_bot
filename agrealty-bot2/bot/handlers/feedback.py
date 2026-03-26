"""Handler for feedback callbacks."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
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

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "fb:up")
async def handle_feedback_up(callback: CallbackQuery) -> None:
    """Handle positive feedback (👍)."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} gave positive feedback")
    
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
    username = callback.from_user.username or "N/A"
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
    
    # Get history
    history = get_last_history(user_id, n=10)
    history_text = "\n".join(history) if history else "История пуста"
    
    # Send to admins if configured
    admin_ids = [a for a in getattr(Config, "ADMIN_CHAT_IDS", []) if a > 0] or ([Config.ADMIN_CHAT_ID] if Config.ADMIN_CHAT_ID > 0 else [])
    if admin_ids:
        feedback_message = (
            f"👎 Feedback\n"
            f"Reason: {reason_name}\n"
            f"User: {user_id} @{username}\n"
            f"Section: {last_section}\n"
            f"Q: {last_question}\n"
            f"A: {last_answer}\n"
            f"History:\n{history_text}"
        )
        for aid in admin_ids:
            try:
                await callback.message.bot.send_message(aid, feedback_message)
                logger.info(f"Feedback sent to admin {aid}")
            except Exception as e:
                logger.error(f"Failed to send feedback to admin {aid}: {e}")
    
    # Save reason
    await state.update_data(last_feedback_reason=reason_name)
    
    # If "other" - ask for comment
    if reason_data == "fb:reason:other":
        await callback.message.answer(FEEDBACK_DOWN_ASK_OTHER)
        await state.set_state(FeedbackState.awaiting_other_comment)
    else:
        # Just thank and finish
        await callback.message.answer(FEEDBACK_DOWN_THANKS)
        # Don't clear state, preserve selected_section


@router.message(FeedbackState.awaiting_other_comment)
async def handle_feedback_other_comment(message: Message, state: FSMContext) -> None:
    """Handle comment for 'other' feedback reason."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    comment = message.text
    logger.info(f"User {user_id} provided feedback comment: {comment}")
    
    # Get data
    data = await state.get_data()
    reason = data.get("last_feedback_reason", "📝 другое")
    selected_section = data.get("selected_section")
    
    # Send to admins if configured
    admin_ids = [a for a in getattr(Config, "ADMIN_CHAT_IDS", []) if a > 0] or ([Config.ADMIN_CHAT_ID] if Config.ADMIN_CHAT_ID > 0 else [])
    if admin_ids:
        feedback_message = (
            f"👎 Feedback\n"
            f"Reason: {reason}\n"
            f"Other comment: {comment}\n"
            f"User: {user_id} @{username}\n"
            f"Section: {data.get('last_section', '')}\n"
            f"Q: {data.get('last_question_text', '')}\n"
            f"A: {data.get('last_answer_text', '')}\n"
        )
        history = get_last_history(user_id, n=10)
        if history:
            feedback_message += f"History:\n{chr(10).join(history)}"
        
        for aid in admin_ids:
            try:
                await message.bot.send_message(aid, feedback_message)
                logger.info(f"Feedback with comment sent to admin {aid}")
            except Exception as e:
                logger.error(f"Failed to send feedback to admin {aid}: {e}")
    
    # Thank user
    await message.answer(FEEDBACK_DOWN_THANKS)
    
    # Clear feedback state but preserve selected_section
    await state.clear()
    if selected_section:
        await state.set_state(MenuState.selected_section)
        await state.update_data(selected_section=selected_section)

