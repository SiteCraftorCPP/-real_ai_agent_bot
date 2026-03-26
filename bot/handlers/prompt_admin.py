"""Админка: просмотр и замена CORE system prompt для GPT (через Telegram)."""
from __future__ import annotations

import io
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.keyboards import get_prompt_admin_kb, get_admin_panel_kb, get_prompt_dynamic_kb
from bot.prompt_dynamic_store import (
    get_dynamic_block,
    save_dynamic_block,
)
from bot.prompt_store import (
    MAX_PROMPT_CHARS,
    SYSTEM_PROMPT_OVERRIDE_PATH,
    can_edit_prompt,
    get_core_prompt,
    save_core_prompt,
    uses_bundled_default,
)
from bot.handlers.admin import is_admin, is_prompt_only_editor

logger = logging.getLogger(__name__)
router = Router()

TELEGRAM_TEXT_LIMIT = 4000


class PromptAdminStates(StatesGroup):
    waiting_new_prompt = State()
    waiting_dyn_text = State()


DYN_KEY_MAP = {
    "fb": "feedback",
    "pr": "pricing",
    "rd": "risks_docs",
    "sp": "specialist_request",
}


def _split_for_telegram(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    if not text:
        return ["(пусто)"]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _prompt_status_line() -> str:
    core = get_core_prompt()
    src = (
        "встроенный из кода (bot/texts.py)"
        if uses_bundled_default()
        else f"файл data/{SYSTEM_PROMPT_OVERRIDE_PATH.name}"
    )
    return (
        "🤖 CORE system prompt\n\n"
        f"Источник: {src}\n"
        f"Длина: {len(core)} символов\n"
        f"Макс. при загрузке: {MAX_PROMPT_CHARS}\n"
    )


@router.callback_query(F.data == "admin:prompt")
async def cb_prompt_menu(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    text = _prompt_status_line() + "\nВыберите действие:"
    await callback.message.edit_text(
        text,
        reply_markup=get_prompt_admin_kb(),
    )


@router.callback_query(F.data == "admin:prompt:full")
async def cb_prompt_full(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Отправляю частями…")
    core = get_core_prompt()
    for i, chunk in enumerate(_split_for_telegram(core)):
        prefix = f"📄 Часть {i + 1}\n\n"
        await callback.message.answer(prefix + chunk)


@router.callback_query(F.data == "admin:prompt:download")
async def cb_prompt_download(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    core = get_core_prompt()
    raw = core.encode("utf-8")
    name = "system_prompt_core_active.txt"
    await callback.message.answer_document(
        BufferedInputFile(raw, filename=name),
        caption="Текущий CORE system prompt (UTF-8).",
    )


@router.callback_query(F.data == "admin:prompt:edit")
async def cb_prompt_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.set_state(PromptAdminStates.waiting_new_prompt)
    await callback.message.answer(
        "✏️ Пришлите новый CORE prompt одним сообщением или файлом .txt / .md (UTF-8).\n\n"
        f"Ограничение: до {MAX_PROMPT_CHARS} символов.\n"
        "Отмена: /cancel",
    )


@router.callback_query(F.data == "admin:prompt:back")
async def cb_prompt_back(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    uid = callback.from_user.id
    un = callback.from_user.username
    await callback.message.edit_text(
        "🔐 Админ-панель\n\nВыберите действие:",
        reply_markup=get_admin_panel_kb(
            show_prompt=can_edit_prompt(uid, un),
            prompt_only=is_prompt_only_editor(uid, un),
        ),
    )


@router.callback_query(F.data == "admin:prompt:dyn")
async def cb_prompt_dyn_menu(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ Динамика LLM\n\nВыберите блок/конфиг для просмотра и редактирования:",
        reply_markup=get_prompt_dynamic_kb(),
    )


@router.callback_query(F.data.startswith("admin:prompt:dyn:full:"))
async def cb_prompt_dyn_full(callback: CallbackQuery) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    short_key = callback.data.rsplit(":", 1)[-1]
    item = DYN_KEY_MAP.get(short_key)
    if not item:
        await callback.answer("Неизвестный элемент", show_alert=True)
        return
    await callback.answer("Отправляю…")
    text = get_dynamic_block(item)
    title = f"BLOCK: {item}"
    chunks = _split_for_telegram(text)
    if len(chunks) == 1:
        await callback.message.answer(f"📄 {title}\n\n{chunks[0]}")
    else:
        for i, chunk in enumerate(chunks):
            prefix = f"📄 {title} | часть {i + 1}\n\n"
            await callback.message.answer(prefix + chunk)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin:prompt:dyn:edit:{short_key}")],
            [InlineKeyboardButton(text="« Назад к динамике", callback_data="admin:prompt:dyn")],
        ]
    )
    await callback.message.answer("Выберите действие:", reply_markup=kb)


@router.callback_query(F.data.startswith("admin:prompt:dyn:edit:"))
async def cb_prompt_dyn_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not can_edit_prompt(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    short_key = callback.data.rsplit(":", 1)[-1]
    item = DYN_KEY_MAP.get(short_key)
    if not item:
        await callback.answer("Неизвестный элемент", show_alert=True)
        return
    await callback.answer()
    await state.set_state(PromptAdminStates.waiting_dyn_text)
    await state.update_data(dyn_key=short_key)
    tip = "Пришлите новый текст сообщением или файлом .txt/.md (UTF-8)."
    await callback.message.answer(f"✏️ Редактирование: `{item}`\n\n{tip}\nОтмена: /cancel", parse_mode="Markdown")


@router.message(PromptAdminStates.waiting_new_prompt, F.text == "/cancel")
async def prompt_edit_cancel(message: Message, state: FSMContext) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(PromptAdminStates.waiting_dyn_text, F.text == "/cancel")
async def dyn_edit_cancel(message: Message, state: FSMContext) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(PromptAdminStates.waiting_new_prompt, F.text)
async def prompt_edit_text(message: Message, state: FSMContext) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    text = message.text or ""
    if not text.strip():
        await message.answer("Пустой текст. Пришлите промпт или /cancel.")
        return
    try:
        save_core_prompt(text)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    await message.answer(f"✅ CORE prompt сохранён ({len(text.strip())} символов). Изменения применяются сразу.")


@router.message(PromptAdminStates.waiting_dyn_text, F.text)
async def dyn_edit_text(message: Message, state: FSMContext) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    data = await state.get_data()
    short_key = data.get("dyn_key")
    item = DYN_KEY_MAP.get(short_key or "")
    if not item:
        await state.clear()
        await message.answer("❌ Не удалось определить элемент редактирования.")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст. Пришлите данные или /cancel.")
        return
    try:
        save_dynamic_block(item, text)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    await message.answer(f"✅ Сохранено: {item}. Применяется сразу.")


@router.message(PromptAdminStates.waiting_new_prompt, F.document)
async def prompt_edit_document(message: Message, state: FSMContext, bot: Bot) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    doc = message.document
    if not doc:
        return
    max_bytes = 2 * 1024 * 1024
    if doc.file_size and doc.file_size > max_bytes:
        await message.answer("❌ Файл слишком большой (макс. 2 МБ).")
        return
    file_name = (doc.file_name or "").lower()
    if file_name and not (file_name.endswith(".txt") or file_name.endswith(".md")):
        await message.answer("❌ Пришлите `.txt` или `.md`, либо текстом в сообщении.")
        return

    buf = io.BytesIO()
    try:
        await bot.download(doc, destination=buf)
    except Exception as e:
        logger.error("download prompt file: %s", e, exc_info=True)
        await message.answer("❌ Не удалось скачать файл.")
        return

    raw = buf.getvalue()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        await message.answer("❌ Неверная кодировка. Сохраните файл как UTF-8.")
        return

    try:
        save_core_prompt(text)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    await state.clear()
    await message.answer(f"✅ CORE prompt загружен из файла ({len(text.strip())} символов).")


@router.message(PromptAdminStates.waiting_dyn_text, F.document)
async def dyn_edit_document(message: Message, state: FSMContext, bot: Bot) -> None:
    if not can_edit_prompt(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    data = await state.get_data()
    short_key = data.get("dyn_key")
    item = DYN_KEY_MAP.get(short_key or "")
    if not item:
        await state.clear()
        await message.answer("❌ Не удалось определить элемент редактирования.")
        return
    doc = message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > 2 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой (макс. 2 МБ).")
        return
    file_name = (doc.file_name or "").lower()
    if file_name and not (file_name.endswith(".txt") or file_name.endswith(".md")):
        await message.answer("❌ Пришлите `.txt` / `.md`.")
        return
    buf = io.BytesIO()
    try:
        await bot.download(doc, destination=buf)
    except Exception as e:
        logger.error("download dynamic file: %s", e, exc_info=True)
        await message.answer("❌ Не удалось скачать файл.")
        return
    raw = buf.getvalue()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        await message.answer("❌ Неверная кодировка. Сохраните файл как UTF-8.")
        return
    try:
        save_dynamic_block(item, text)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    await message.answer(f"✅ Сохранено из файла: {item}.")
