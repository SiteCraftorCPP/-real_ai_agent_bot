"""Хранение CORE system prompt для LLM (переопределение через файл)."""
from __future__ import annotations

import logging
from pathlib import Path

from bot.config import project_root
from bot.database import is_db_admin
from bot.texts import SYSTEM_PROMPT_V1_1

logger = logging.getLogger(__name__)

# Переопределение лежит рядом с БД; при наличии файла используется он вместо SYSTEM_PROMPT_V1_1 из кода.
SYSTEM_PROMPT_OVERRIDE_PATH: Path = project_root / "data" / "system_prompt_core.txt"

MAX_PROMPT_CHARS = 500_000


def get_core_prompt() -> str:
    """Текущий CORE system prompt: из файла или встроенный дефолт."""
    if SYSTEM_PROMPT_OVERRIDE_PATH.is_file():
        try:
            return SYSTEM_PROMPT_OVERRIDE_PATH.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Не удалось прочитать %s: %s", SYSTEM_PROMPT_OVERRIDE_PATH, e)
            return SYSTEM_PROMPT_V1_1
    return SYSTEM_PROMPT_V1_1


def uses_bundled_default() -> bool:
    """True, если активен встроенный промпт из кода (файла переопределения нет)."""
    return not SYSTEM_PROMPT_OVERRIDE_PATH.is_file()


def save_core_prompt(text: str) -> None:
    """Атомарно сохранить CORE prompt в файл."""
    text = text.strip()
    if not text:
        raise ValueError("Промпт не может быть пустым.")
    if len(text) > MAX_PROMPT_CHARS:
        raise ValueError(f"Слишком длинный промпт (макс. {MAX_PROMPT_CHARS} символов).")

    SYSTEM_PROMPT_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SYSTEM_PROMPT_OVERRIDE_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(SYSTEM_PROMPT_OVERRIDE_PATH)
    logger.info("CORE system prompt сохранён в %s (%s символов)", SYSTEM_PROMPT_OVERRIDE_PATH, len(text))


def reset_to_bundled() -> None:
    """Удалить файл переопределения — снова используется SYSTEM_PROMPT_V1_1 из кода."""
    if SYSTEM_PROMPT_OVERRIDE_PATH.is_file():
        SYSTEM_PROMPT_OVERRIDE_PATH.unlink()
        logger.info("Переопределение промпта сброшено, используется встроенный CORE из bot/texts.py")


def can_edit_prompt(user_id: int, username: str | None) -> bool:
    """
    Кто может править промпт через Telegram.
    - Любой user_id из ADMIN_CHAT_IDS.
    - Если задан PROMPT_ADMIN_USERNAMES — только эти @username + совпадение по ID выше.
    - Если PROMPT_ADMIN_USERNAMES пуст — как обычный is_admin (username в .env/БД).
    """
    from bot.config import Config

    if user_id in Config.ADMIN_CHAT_IDS:
        return True

    un = (username or "").strip().lstrip("@").lower()
    if not un:
        return False

    if Config.PROMPT_ADMIN_USERNAMES:
        return un in Config.PROMPT_ADMIN_USERNAMES

    if un in Config.ADMIN_USERNAMES:
        return True
    return is_db_admin(username)
