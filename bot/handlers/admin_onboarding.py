"""Админка: текст приветствия /start (сообщение 1) через data/onboarding_text.txt."""
from __future__ import annotations

import io
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, BufferedInputFile, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.handlers.admin import is_admin
from bot.keyboards import get_onboarding_admin_kb, get_admin_panel_kb
from bot.onboarding_store import (
    MAX_ONBOARDING_CHARS,
    get_onboarding_text,
    save_onboarding_text,
    uses_default_onboarding,
    ONBOARDING_OVERRIDE_PATH,
)
from bot.prompt_store import can_edit_prompt
from bot.handlers.admin import is_prompt_only_editor

logger = logging.getLogger(__name__)
router = Router()

TELEGRAM_TEXT_LIMIT = 4096


class OnboardingAdminStates(StatesGroup):
    waiting_txt_file = State()


def _status_text() -> str:
    src = "встроенный (bot/texts.py)" if uses_default_onboarding() else f"файл `{ONBOARDING_OVERRIDE_PATH.name}`"
    body = get_onboarding_text()
    return (
        "👋 *Приветствие /start* (первое сообщение онбординга)\n\n"
        f"Источник: {src}\n"
        f"Длина: {len(body)} символов\n"
        f"Макс. при загрузке: {MAX_ONBOARDING_CHARS}\n\n"
        "Выберите действие:"
    )


def _split_chunks(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    if not text:
        return ["(пусто)"]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


@router.callback_query(F.data == "admin:onboarding")
async def cb_onboarding_menu(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _status_text(),
        reply_markup=get_onboarding_admin_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:onboarding:full")
async def cb_onboarding_full(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Отправляю частями…")
    text = get_onboarding_text()
    chunks = _split_chunks(text)
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        prefix = f"📄 Приветствие | часть {i + 1}/{n}\n\n" if n > 1 else ""
        await callback.message.answer(prefix + chunk)


@router.callback_query(F.data == "admin:onboarding:download")
async def cb_onboarding_download(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    raw = get_onboarding_text().encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(raw, filename="onboarding_text_active.txt"),
        caption="Текущий текст приветствия (UTF-8).",
    )


@router.callback_query(F.data == "admin:onboarding:edit")
async def cb_onboarding_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.set_state(OnboardingAdminStates.waiting_txt_file)
    await callback.message.answer(
        f"✏️ Пришлите новый текст приветствия *файлом* `.txt` (UTF-8).\n\n"
        f"До {MAX_ONBOARDING_CHARS} символов.\n"
        "Отмена: /cancel",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:onboarding:back")
async def cb_onboarding_back(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    uid = callback.from_user.id
    un = callback.from_user.username
    from bot.database import get_bot_users_stats

    opening = "🔐 *Админ-панель*"
    try:
        n = get_bot_users_stats()["total"]
        opening += f"\n\n👥 Подписчиков: *{n}*"
    except Exception:
        pass
    opening += "\n\nВыберите действие:"
    await callback.message.edit_text(
        opening,
        reply_markup=get_admin_panel_kb(
            show_prompt=can_edit_prompt(uid, un),
            prompt_only=is_prompt_only_editor(uid, un),
            full_admin_tools=is_admin(uid, un),
        ),
        parse_mode="Markdown",
    )


@router.message(OnboardingAdminStates.waiting_txt_file, Command("cancel"))
async def onboarding_edit_cancel(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(OnboardingAdminStates.waiting_txt_file, F.document)
async def onboarding_edit_document(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    doc = message.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await message.answer("❌ Нужен файл `.txt`. Отмена: /cancel")
        return
    if doc.file_size and doc.file_size > 2 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой (макс. 2 МБ).")
        await state.clear()
        return
    buf = io.BytesIO()
    try:
        await bot.download(doc, destination=buf)
        raw = buf.getvalue()
        text = raw.decode("utf-8")
        save_onboarding_text(text)
        await message.answer(f"✅ Приветствие обновлено ({len(text)} символов).")
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        logger.error("onboarding save: %s", e, exc_info=True)
        await message.answer("❌ Ошибка при чтении файла.")
    await state.clear()


@router.message(OnboardingAdminStates.waiting_txt_file, F.text)
async def onboarding_edit_deny_text(message: Message) -> None:
    if not is_admin(message.from_user.id, message.from_user.username):
        return
    await message.answer("❌ Пришлите файл `.txt` (UTF-8). Отмена: /cancel")
