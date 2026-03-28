"""Handler for /start command."""
import os
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.config import Config
from bot.database import mark_onboarding_shown, upsert_bot_user
from bot.keyboards import get_main_menu_inline
from bot.texts import (
    ONBOARDING_TEXT,
    ONBOARDING_STEP3_TEXT,
)

logger = logging.getLogger(__name__)
router = Router()

# v1.3.5: Имя файла для отображения при отправке PDF
PDF_DISPLAY_FILENAME = "Аналитика рынка недвижимости Санкт‑Петербурга и Москвы (2025).pdf"


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command: send logo (if exists), onboarding text, and main menu.
    v1.3.6 FINAL (ТЗ): строго 3 сообщения:
    1) Приветствие + ценность
    2) PDF без текста/подписи (только при первом заходе)
    3) Текст + CTA, и дальше inline-меню."""
    user_id = message.from_user.id
    username = message.from_user.username
    logger.info(f"User {user_id} (@{username}) sent /start")
    upsert_bot_user(user_id, username)

    # Reset state
    await state.clear()

    # 1) Сообщение 1: приветствие + ценность (без CTA/меню)
    await message.answer(ONBOARDING_TEXT)

    # PDF на сообщение 2: всегда пытаемся отправить при каждом /start
    # (если отправка не удалась — не маркируем onboarding, чтобы можно было повторить).
    pdf_path = Path(Config.KEY_FIGURES_PDF_PATH)
    if pdf_path.exists():
        try:
            document = FSInputFile(
                str(pdf_path),
                filename=PDF_DISPLAY_FILENAME,
            )
            await message.answer_document(document=document)
            # Маркируем onboarding только после успешной отправки файла.
            mark_onboarding_shown(user_id)
        except Exception as e:
            logger.error(f"Failed to send PDF: {e}", exc_info=True)
    else:
        logger.warning(f"Key figures PDF not found: {pdf_path}")

    # 3) Сообщение 3: короткий текст + CTA и меню
    await message.answer(ONBOARDING_STEP3_TEXT, reply_markup=get_main_menu_inline())


@router.callback_query(F.data == "onboarding:key_figures")
async def cb_onboarding_key_figures(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle 'Посмотреть ключевые цифры' button (legacy): send PDF and follow-up message."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} clicked onboarding:key_figures")

    await callback.answer()

    pdf_path = Path(Config.KEY_FIGURES_PDF_PATH)
    if not pdf_path.exists():
        logger.warning(f"Key figures PDF not found: {pdf_path}")
        await callback.message.answer(
            "Файл с аналитикой временно недоступен. Попробуйте позже или задайте вопрос в чат."
        )
    else:
        try:
            document = FSInputFile(
                str(pdf_path),
                filename=PDF_DISPLAY_FILENAME
            )
            await callback.message.answer_document(document=document)
        except Exception as e:
            logger.error(f"Failed to send PDF: {e}", exc_info=True)
            await callback.message.answer("Не удалось отправить файл. Попробуйте позже.")

    # В любом случае показываем сообщение 3 (меню) как в ТЗ
    await callback.message.answer(ONBOARDING_STEP3_TEXT, reply_markup=get_main_menu_inline())
