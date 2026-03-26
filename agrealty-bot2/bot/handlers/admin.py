"""Admin panel (minimal) for prompt management."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.keyboards import get_admin_panel_kb
from bot.prompt_store import can_edit_prompt

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int, username: str | None = None) -> bool:
    if user_id in Config.ADMIN_CHAT_IDS:
        return True
    if username and username.lower() in Config.ADMIN_USERNAMES:
        return True
    return False


def is_prompt_only_editor(user_id: int, username: str | None) -> bool:
    return can_edit_prompt(user_id, username) and not is_admin(user_id, username)


@router.message(Command("admin"))
async def handle_admin_panel(message: Message) -> None:
    uid = message.from_user.id
    un = message.from_user.username
    if not is_admin(uid, un) and not can_edit_prompt(uid, un):
        return

    await message.answer(
        "🔐 Админ-панель\n\nВыберите действие:",
        reply_markup=get_admin_panel_kb(
            show_prompt=can_edit_prompt(uid, un),
            prompt_only=is_prompt_only_editor(uid, un),
        ),
    )

