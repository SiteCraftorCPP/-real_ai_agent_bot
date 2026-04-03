"""Рассылка одного сообщения всем пользователям из bot_users (только полные админы)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import get_all_bot_user_ids
from bot.handlers.admin import is_admin

logger = logging.getLogger(__name__)
router = Router()

_BROADCAST_DELAY_SEC = 0.05


class BroadcastStates(StatesGroup):
    waiting_message = State()


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data="admin:broadcast:go"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin:broadcast:cancel"),
            ]
        ]
    )


async def _run_broadcast(
    bot: Bot,
    *,
    from_chat_id: int,
    message_id: int,
    notify_chat_id: int,
) -> None:
    user_ids = get_all_bot_user_ids()
    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
        except Exception as e:
            logger.debug("broadcast skip user %s: %s", uid, e)
        await asyncio.sleep(_BROADCAST_DELAY_SEC)
    try:
        await bot.send_message(notify_chat_id, "Готово.")
    except Exception as e:
        logger.warning("broadcast notify admin: %s", e)


@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id
    un = callback.from_user.username
    if not is_admin(uid, un):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BroadcastStates.waiting_message)
    await callback.message.answer(
        "📢 *Рассылка*\n\n"
        "Пришлите *одно* сообщение — его получат все пользователи из базы бота "
        "(подойдут текст, фото, видео, документ и т.п.).\n\n"
        "Отмена: /cancel",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id
    un = callback.from_user.username
    if not is_admin(uid, un):
        await callback.answer()
        return
    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.edit_text("Рассылка отменена.")
    except Exception:
        pass


@router.callback_query(F.data == "admin:broadcast:go")
async def cb_broadcast_go(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    uid = callback.from_user.id
    un = callback.from_user.username
    if not is_admin(uid, un):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    from_chat_id = data.get("bc_from_chat_id")
    message_id = data.get("bc_message_id")
    if from_chat_id is None or message_id is None:
        await callback.answer("Нет данных — начните заново", show_alert=True)
        await state.clear()
        return
    await state.clear()
    await callback.answer("Запуск…")
    try:
        await callback.message.edit_text("Рассылка выполняется…")
    except Exception:
        pass
    notify_chat_id = callback.message.chat.id
    asyncio.create_task(
        _run_broadcast(
            bot,
            from_chat_id=int(from_chat_id),
            message_id=int(message_id),
            notify_chat_id=notify_chat_id,
        )
    )


@router.message(BroadcastStates.waiting_message, Command("cancel"))
async def broadcast_cancel_cmd(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(BroadcastStates.waiting_message)
async def broadcast_got_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    if message.text and message.text.startswith("/"):
        await message.answer("Неизвестная команда. Для отмены: /cancel")
        return
    await state.update_data(bc_from_chat_id=message.chat.id, bc_message_id=message.message_id)
    await message.answer(
        "Такое сообщение уйдёт всем пользователям из базы. Подтвердите:",
        reply_markup=_confirm_kb(),
    )
