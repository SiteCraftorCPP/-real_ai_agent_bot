"""Handlers for specialist consultation request flow."""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from bot.state import SpecialistRequest, FeedbackState, MenuState
from bot.texts import (
    SPECIALIST_START,
    SPECIALIST_ASK_TYPE,
    SPECIALIST_ASK_GOAL,
    SPECIALIST_ASK_BUDGET,
    SPECIALIST_ASK_URGENCY,
    SPECIALIST_ASK_DETAILS,
    SPECIALIST_DONE_USER,
    SPECIALIST_DONE_USER_NO_ADMIN,
    SPECIALIST_CANCELLED,
)
from bot.keyboards import get_cancel_kb, get_main_menu_inline
from bot.config import Config
from bot.context import (
    get_session_context,
    update_session_context,
    is_question_asked,
    mark_question_asked,
    get_current_session_id,
    get_session_history_from_state,
    format_session_for_file,
)
from bot.database import get_session_info

logger = logging.getLogger(__name__)
router = Router()


async def handle_cancel(message: Message, state: FSMContext) -> None:
    """Handle cancel command or button - exit specialist flow."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    
    # Save selected_section before clearing
    data = await state.get_data()
    selected_section = data.get("selected_section")
    
    # Clear state
    await state.clear()
    
    # Restore selected_section if it was set
    if selected_section:
        await state.set_state(MenuState.selected_section)
        await state.update_data(selected_section=selected_section)
    
    logger.info(f"User {user_id} (@{username}) cancelled specialist consultation")
    
    await message.answer(
        SPECIALIST_CANCELLED,
        reply_markup=get_main_menu_inline()
    )


@router.message(F.text.in_(["/cancel", "❌ Отмена"]))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Handle /cancel command or cancel button."""
    current_state = await state.get_state()
    
    # Only handle cancel if in specialist flow
    if current_state and current_state.startswith("SpecialistRequest"):
        await handle_cancel(message, state)


@router.message(SpecialistRequest.city)
async def handle_city(message: Message, state: FSMContext) -> None:
    """Handle city input - first step of specialist consultation."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    city = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Save city using context
    await update_session_context(state, "location.city", city, asked_question="city")
    # Также сохраняем для обратной совместимости
    await state.update_data(city=city)
    logger.info(f"User {user_id} (@{username}) entered city: {city}")
    
    # Move to next state - check if property_type already exists
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("object_type"):
        # Skip property_type, go to request_type
        await handle_property_type_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.property_type)
        await message.answer(
            SPECIALIST_ASK_TYPE,
            reply_markup=get_cancel_kb()
        )


async def handle_property_type_skip(message: Message, state: FSMContext) -> None:
    """Skip property_type question if already in data."""
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("request_type"):
        # Skip request_type too, go to budget
        await handle_request_type_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.request_type)
        await message.answer(
            SPECIALIST_ASK_GOAL,
            reply_markup=get_cancel_kb()
        )


@router.message(SpecialistRequest.property_type)
async def handle_property_type(message: Message, state: FSMContext) -> None:
    """Handle property type input - second step."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    property_type = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Save property_type using context
    await update_session_context(state, "object_type", property_type, asked_question="property_type")
    # Также сохраняем для обратной совместимости
    await state.update_data(property_type=property_type)
    logger.info(f"User {user_id} (@{username}) entered property_type: {property_type}")
    
    # Move to next state - check if request_type already exists
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("request_type"):
        # Skip request_type, go to budget
        await handle_request_type_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.request_type)
        await message.answer(
            SPECIALIST_ASK_GOAL,
            reply_markup=get_cancel_kb()
        )


async def handle_request_type_skip(message: Message, state: FSMContext) -> None:
    """Skip request_type question if already in data."""
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("budget"):
        # Skip budget too, go to urgency
        await handle_budget_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.budget)
        await message.answer(
            SPECIALIST_ASK_BUDGET,
            reply_markup=get_cancel_kb()
        )


@router.message(SpecialistRequest.request_type)
@router.message(SpecialistRequest.goal)  # Backward compatibility
async def handle_request_type(message: Message, state: FSMContext) -> None:
    """Handle request_type input - third step (renamed from goal)."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    request_type = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Save request_type using context
    await update_session_context(state, "request_type", request_type, asked_question="request_type")
    # Также сохраняем для обратной совместимости
    await state.update_data(request_type=request_type, goal=request_type)
    logger.info(f"User {user_id} (@{username}) entered request_type: {request_type}")
    
    # Move to next state - check if budget already exists
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("budget"):
        # Skip budget, go to urgency
        await handle_budget_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.budget)
        await message.answer(
            SPECIALIST_ASK_BUDGET,
            reply_markup=get_cancel_kb()
        )


async def handle_budget_skip(message: Message, state: FSMContext) -> None:
    """Skip budget question if already in data."""
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("urgency"):
        # Skip urgency too, go to details
        await handle_urgency_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.urgency)
        await message.answer(
            SPECIALIST_ASK_URGENCY,
            reply_markup=get_cancel_kb()
        )


@router.message(SpecialistRequest.budget)
async def handle_budget(message: Message, state: FSMContext) -> None:
    """Handle budget input - fourth step."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    budget = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Save budget using context
    await update_session_context(state, "budget", budget, asked_question="budget")
    # Также сохраняем для обратной совместимости
    await state.update_data(budget=budget)
    logger.info(f"User {user_id} (@{username}) entered budget: {budget}")
    
    # Move to next state - check if urgency already exists
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    if collected_data.get("urgency"):
        # Skip urgency, go to details
        await handle_urgency_skip(message, state)
    else:
        await state.set_state(SpecialistRequest.urgency)
        await message.answer(
            SPECIALIST_ASK_URGENCY,
            reply_markup=get_cancel_kb()
        )


async def handle_urgency_skip(message: Message, state: FSMContext) -> None:
    """Skip urgency question if already in data."""
    await state.set_state(SpecialistRequest.details)
    await message.answer(
        SPECIALIST_ASK_DETAILS,
        reply_markup=get_cancel_kb()
    )


@router.message(SpecialistRequest.urgency)
async def handle_urgency(message: Message, state: FSMContext) -> None:
    """Handle urgency input - fifth step."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    urgency = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Save urgency using context
    await update_session_context(state, "urgency", urgency, asked_question="urgency")
    # Также сохраняем для обратной совместимости
    await state.update_data(urgency=urgency)
    logger.info(f"User {user_id} (@{username}) entered urgency: {urgency}")
    
    # Move to next state
    await state.set_state(SpecialistRequest.details)
    await message.answer(
        SPECIALIST_ASK_DETAILS,
        reply_markup=get_cancel_kb()
    )


async def send_specialist_request_with_history(
    bot,
    state: FSMContext,
    user_id: int,
    username: str | None,
    chat_id: int,
    section: str | None = None
) -> None:
    """
    Send session history as .txt file to admin chat for specialist consultation.
    
    Args:
        bot: Bot instance
        state: FSM context
        user_id: Telegram user ID
        username: Telegram username
        chat_id: Target chat ID (admin private chat)
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
            "section": section or data.get("session_section") or data.get("selected_section") or "не выбран",
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
        
        await bot.send_document(
            chat_id=chat_id,
            document=file,
            caption=f"📎 История сессии для user {user_id}"
        )
        logger.info(f"Session history file sent to admin chat {chat_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send session history file: {e}", exc_info=True)


@router.message(SpecialistRequest.details)
async def handle_details(message: Message, state: FSMContext) -> None:
    """Handle details input - final step, send request to admin."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    details = message.text
    
    # Check if user is in feedback state (should not happen, but safety check)
    current_state = await state.get_state()
    if current_state == FeedbackState.awaiting_comment or current_state == FeedbackState.awaiting_other_comment:
        return
    
    # Get all collected data using context
    context = await get_session_context(state)
    collected_data = context.get("collected_data", {})
    data = await state.get_data()
    
    # Получаем данные из collected_data (новый формат)
    location = collected_data.get("location", {})
    city = location.get("city") or data.get("city", "не указан")
    property_type = collected_data.get("object_type") or data.get("property_type", "не указан")
    request_type = collected_data.get("request_type") or data.get("request_type") or data.get("goal", "не указан")
    budget = collected_data.get("budget") or data.get("budget", "не указан")
    urgency = collected_data.get("urgency") or data.get("urgency", "не указана")
    original_request = data.get("original_request_text", "")  # If user started from free text
    selected_section = data.get("selected_section")
    
    # Save details
    await state.update_data(details=details)
    logger.info(f"User {user_id} (@{username}) entered details: {details}")
    
    # Get current date/time
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Form admin message with clickable username
    if username != "N/A":
        user_link = f'<a href="tg://user?id={user_id}">@{username}</a>'
    else:
        user_link = f'<a href="tg://user?id={user_id}">{user_id}</a>'
    
    admin_message = (
        f"📩 Новая заявка (консультация специалиста)\n"
        f"Дата и время: {date_time}\n"
        f"User: {user_link} (ID: {user_id})\n"
        f"Тип запроса: {request_type}\n"
        f"Тип объекта: {property_type}\n"
        f"Город/район: {city}\n"
        f"Бюджет: {budget}\n"
        f"Срочность: {urgency}\n"
    )
    
    if original_request:
        admin_message += f"Исходный запрос: {original_request}\n"
    
    admin_message += f"Детали: {details}"
    
    # Send to all admins (IDs from .env: ADMIN_CHAT_IDS ∪ ADMIN_CHAT_ID)
    admin_ids = [a for a in Config.ADMIN_CHAT_IDS if a > 0]
    if admin_ids:
        sent_ok = False
        last_err = None
        for aid in admin_ids:
            try:
                await message.bot.send_message(aid, admin_message, parse_mode="HTML")
                logger.info(f"Specialist request sent to admin {aid} from user {user_id}")
                await send_specialist_request_with_history(
                    bot=message.bot,
                    state=state,
                    user_id=user_id,
                    username=username if username != "N/A" else None,
                    chat_id=aid,
                    section=selected_section
                )
                sent_ok = True
            except Exception as e:
                last_err = e
                logger.error(f"Failed to send specialist request to admin {aid}: {e}")
        if sent_ok:
            user_response = SPECIALIST_DONE_USER
        else:
            logger.warning(
                "Could not notify any admin (ADMIN_CHAT_IDS=%s): %s",
                admin_ids,
                last_err,
            )
            user_response = SPECIALIST_DONE_USER_NO_ADMIN
    else:
        logger.warning("No admin IDs in .env (ADMIN_CHAT_IDS / ADMIN_CHAT_ID), request not sent to admins")
        user_response = SPECIALIST_DONE_USER_NO_ADMIN
    
    # Clear specialist state but preserve selected_section
    await state.clear()
    if selected_section:
        await state.set_state(MenuState.selected_section)
        await state.update_data(selected_section=selected_section)
    
    # Send confirmation to user
    await message.answer(
        user_response,
        reply_markup=get_main_menu_inline()
    )
    
    logger.info(f"Specialist consultation flow completed for user {user_id}")

