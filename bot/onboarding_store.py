"""Текст приветствия /start (сообщение 1): переопределение через data/onboarding_text.txt."""
from __future__ import annotations

import logging
from pathlib import Path

from bot.config import project_root
from bot.texts import ONBOARDING_TEXT as DEFAULT_ONBOARDING_TEXT

logger = logging.getLogger(__name__)

ONBOARDING_OVERRIDE_PATH: Path = project_root / "data" / "onboarding_text.txt"
MAX_ONBOARDING_CHARS = 3900


def get_onboarding_text() -> str:
    if ONBOARDING_OVERRIDE_PATH.is_file():
        try:
            return ONBOARDING_OVERRIDE_PATH.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Не удалось прочитать %s: %s", ONBOARDING_OVERRIDE_PATH, e)
            return DEFAULT_ONBOARDING_TEXT
    return DEFAULT_ONBOARDING_TEXT


def uses_default_onboarding() -> bool:
    return not ONBOARDING_OVERRIDE_PATH.is_file()


def save_onboarding_text(text: str) -> None:
    text = (text or "").strip()
    if not text:
        raise ValueError("Текст приветствия не может быть пустым.")
    if len(text) > MAX_ONBOARDING_CHARS:
        raise ValueError(f"Слишком длинный текст (макс. {MAX_ONBOARDING_CHARS} символов).")

    ONBOARDING_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ONBOARDING_OVERRIDE_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ONBOARDING_OVERRIDE_PATH)
    logger.info(
        "Приветствие сохранено в %s (%s символов)",
        ONBOARDING_OVERRIDE_PATH,
        len(text),
    )
