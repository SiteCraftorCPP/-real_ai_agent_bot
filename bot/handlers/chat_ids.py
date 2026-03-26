"""Commands to print chat id and known forum subtopics (message_thread_id)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database import get_forum_threads, upsert_forum_thread

router = Router()


@router.message(Command("chatids"))
async def cmd_chatids(message: Message) -> None:
    chat = message.chat
    thread_id = getattr(message, "message_thread_id", None)
    chat_id = getattr(chat, "id", None)

    # Remember this topic for later listing.
    if chat_id and thread_id:
        upsert_forum_thread(chat_id=chat_id, thread_id=thread_id)

    known_topics = get_forum_threads(chat_id) if chat_id else []

    parts: list[str] = []
    parts.append("🧾 Chat identifiers")
    parts.append(f"chat.id: {chat_id}")
    parts.append(f"chat.title: {getattr(chat, 'title', None)}")
    parts.append(f"chat.username: {getattr(chat, 'username', None)}")
    parts.append(f"chat.type: {getattr(chat, 'type', None)}")
    parts.append(f"user: {message.from_user.id} @{message.from_user.username}")

    if thread_id:
        parts.append(f"topic (message_thread_id): {thread_id}")
    else:
        parts.append("topic (message_thread_id): — (не форум/не топик)")

    if known_topics:
        parts.append("")
        parts.append("Known topics in this chat (bot remembers ones where /chatids was executed):")
        for t in known_topics:
            parts.append(f"- {t['thread_id']} (last_seen_at={t['last_seen_at']})")
    else:
        parts.append("")
        parts.append("To list all subtopics: open each topic and run /chatids there once.")

    await message.answer("\n".join(parts))

