"""Editable storage for dynamic LLM blocks and runtime prompt config."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from bot.config import project_root
from bot.texts import (
    BLOCK_CONTEXT_REMINDER_V1_3_4,
    BLOCK_FEEDBACK_V1_3_4,
    BLOCK_PRICING_V1_3_4,
    BLOCK_RISKS_DOCS_V1_3_4,
    BLOCK_SPECIALIST_REQUEST_V1_3_4,
)

logger = logging.getLogger(__name__)

DATA_DIR = project_root / "data"
RUNTIME_CONFIG_PATH: Path = DATA_DIR / "prompt_runtime_config.json"

BLOCK_KEYS = ("feedback", "pricing", "risks_docs", "specialist_request", "context_reminder")
DEFAULT_BLOCKS: dict[str, str] = {
    "feedback": BLOCK_FEEDBACK_V1_3_4,
    "pricing": BLOCK_PRICING_V1_3_4,
    "risks_docs": BLOCK_RISKS_DOCS_V1_3_4,
    "specialist_request": BLOCK_SPECIALIST_REQUEST_V1_3_4,
    "context_reminder": BLOCK_CONTEXT_REMINDER_V1_3_4,
}
BLOCK_FILES: dict[str, Path] = {k: DATA_DIR / f"system_prompt_block_{k}.txt" for k in BLOCK_KEYS}

DEFAULT_RUNTIME_CONFIG: dict = {
    "priority_order": ["feedback", "pricing", "risks_docs", "specialist_request"],
    "patterns": {
        "feedback": [
            r"некорректн", r"ошибк", r"не\s+так", r"неверн", r"неправильн",
            r"не\s+точн", r"не\s+соглас", r"👎", r"исправ",
        ],
        "pricing": [
            r"цен[аыу]", r"стоимост", r"сколько\s+стоит", r"оцен",
            r"₽", r"руб", r"млн", r"тыс", r"м²", r"кв\.?\s*м",
            r"бюджет", r"за\s+сколько", r"почём", r"дорого", r"дёшево",
            r"выгодн", r"торг", r"скидк",
        ],
        "risks_docs": [
            r"договор", r"контракт", r"документ", r"риск", r"налог",
            r"провер", r"ипотек", r"обремен", r"залог", r"собственн",
            r"юрид", r"право", r"регистрац", r"сделк", r"нотариус",
            r"выписк", r"егрн", r"кадастр", r"справк",
        ],
        "specialist_request": [
            r"(?:нужен|нужна|хочу|дай)\s+(?:консультант|специалист|эксперт|человек)",
            r"подключи\w*\s+(?:специалист|консультант|эксперт)",
            r"кто\s+может\s+помочь",
            r"кому\s+обратиться",
            r"к\s+кому\s+обратиться",
            r"более\s+точн\w+\s+оценк",
            r"(?:нужна|хочу|можно)\s+консультаци",
            r"(?:свяжите|соедините|подключите)\s+(?:меня\s+)?(?:с|со)\s+(?:специалист|консультант|эксперт)",
            r"(?:помоги|помогите)\s+(?:связаться|найти)\s+(?:специалист|консультант)",
        ],
    },
}


def get_dynamic_block(key: str) -> str:
    if key not in DEFAULT_BLOCKS:
        raise ValueError(f"Unknown block key: {key}")
    path = BLOCK_FILES[key]
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Failed to read block override %s: %s", path, e)
    return DEFAULT_BLOCKS[key]


def save_dynamic_block(key: str, text: str) -> None:
    if key not in DEFAULT_BLOCKS:
        raise ValueError(f"Unknown block key: {key}")
    text = (text or "").strip()
    if not text:
        raise ValueError("Текст блока не может быть пустым.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = BLOCK_FILES[key]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def get_runtime_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_RUNTIME_CONFIG))
    if not RUNTIME_CONFIG_PATH.is_file():
        return cfg
    try:
        raw = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
        user_patterns = raw.get("patterns", {})
        for k in ("feedback", "pricing", "risks_docs", "specialist_request"):
            vals = user_patterns.get(k)
            if isinstance(vals, list) and vals and all(isinstance(v, str) for v in vals):
                cfg["patterns"][k] = vals
        order = raw.get("priority_order")
        allowed = {"feedback", "pricing", "risks_docs", "specialist_request"}
        if isinstance(order, list):
            clean = [x for x in order if isinstance(x, str) and x in allowed]
            if clean:
                cfg["priority_order"] = clean
    except Exception as e:
        logger.error("Failed to load runtime prompt config: %s", e, exc_info=True)
    return cfg


def save_runtime_config_from_text(text: str) -> None:
    text = (text or "").strip()
    if not text:
        raise ValueError("Конфиг не может быть пустым.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON: {e}") from e

    patterns = raw.get("patterns")
    if not isinstance(patterns, dict):
        raise ValueError("Поле patterns обязательно и должно быть объектом.")
    for k in ("feedback", "pricing", "risks_docs", "specialist_request"):
        vals = patterns.get(k)
        if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
            raise ValueError(f"patterns.{k} должен быть непустым массивом строк.")

    order = raw.get("priority_order")
    if not isinstance(order, list) or not order:
        raise ValueError("priority_order должен быть непустым массивом.")
    allowed = {"feedback", "pricing", "risks_docs", "specialist_request"}
    if any(x not in allowed for x in order):
        raise ValueError("priority_order содержит недопустимые значения.")

    out = {
        "priority_order": order,
        "patterns": {k: patterns[k] for k in ("feedback", "pricing", "risks_docs", "specialist_request")},
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RUNTIME_CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RUNTIME_CONFIG_PATH)


def get_runtime_config_pretty() -> str:
    return json.dumps(get_runtime_config(), ensure_ascii=False, indent=2)
