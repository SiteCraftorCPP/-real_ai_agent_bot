"""Admin commands for feedback analytics."""
import logging
import csv
import io
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from bot.config import Config
from bot.database import (
    get_stats,
    get_all_feedback,
    add_admin,
    remove_admin,
    get_admins,
    is_db_admin,
    get_all_bot_users,
)
from bot.prompt_store import can_edit_prompt
from bot.keyboards import get_admin_panel_kb, get_export_date_kb, get_admin_manage_kb, get_admin_users_kb
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """States for admin management."""
    waiting_add_username = State()
    waiting_remove_username = State()

logger = logging.getLogger(__name__)
router = Router()

# Лимит длины одного сообщения Telegram (запас под заголовок)
USERS_LIST_CHUNK = 3800


def is_admin(user_id: int, username: str | None = None) -> bool:
    """Check if user is admin by ID, username in .env, or database."""
    # Check by ID (primary admin + optional extra admins)
    if user_id in Config.ADMIN_CHAT_IDS:
        return True
    # Check by username in .env
    if username and username.lower() in Config.ADMIN_USERNAMES:
        return True
    # Check in database
    if is_db_admin(username):
        return True
    return False


def is_prompt_only_editor(user_id: int, username: str | None) -> bool:
    """Доступ к /admin только к промпту: в PROMPT_ADMIN_USERNAMES, но не полноценный админ."""
    return can_edit_prompt(user_id, username) and not is_admin(user_id, username)


# === Helper functions ===

def _truncate(text: str, max_len: int = 100) -> str:
    """Truncate text for readability."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _format_date(iso_date: str) -> str:
    """Format ISO date to readable format."""
    try:
        dt = datetime.fromisoformat(iso_date)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return iso_date


def _format_users_list_for_telegram() -> str:
    """Компактный список для отображения в Telegram."""
    rows = get_all_bot_users()
    if not rows:
        return (
            "📋 Список пользователей\n\n"
            "user_id, username\n\n"
            "Пока нет записанных пользователей."
        )
    out_lines = [
        "📋 Список пользователей",
        "",
        "user_id, username",
        "",
    ]
    for r in rows:
        uid = r["user_id"]
        un = (r.get("username") or "").strip()
        udisp = f"@{un}" if un else "—"
        out_lines.append(f"{uid}, {udisp}")
    return "\n".join(out_lines)


def _users_txt_bytes() -> bytes:
    """Тот же смысл, что список в Telegram: только user_id и username (TSV)."""
    header = "user_id\tusername\n"
    rows = get_all_bot_users()
    body_lines = []
    for r in rows:
        uid = r["user_id"]
        un = (r.get("username") or "").strip().replace("\t", " ")
        ucol = f"@{un}" if un else "—"
        body_lines.append(f"{uid}\t{ucol}")
    text = header + "\n".join(body_lines)
    return ("\ufeff" + text).encode("utf-8")


def _split_chunks(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + limit])
        start += limit
    return chunks


def _format_rating(rating: str) -> str:
    """Format rating to emoji."""
    return "👍" if rating == "positive" else "👎"


def _build_report() -> str:
    """Build statistics report text."""
    stats = get_stats()
    total = stats["total"]
    positive = stats["positive"]
    negative = stats["negative"]
    
    if total == 0:
        return "📊 Пока нет данных по фидбеку."
    
    pos_pct = round(positive / total * 100) if total > 0 else 0
    neg_pct = round(negative / total * 100) if total > 0 else 0
    
    report = f"📊 *Статистика фидбека*\n\n"
    report += f"Всего отзывов: {total}\n"
    report += f"👍 Положительных: {positive} ({pos_pct}%)\n"
    report += f"👎 Отрицательных: {negative} ({neg_pct}%)\n"
    
    reasons = stats.get("reasons", {})
    if reasons:
        report += f"\n*Причины негативных:*\n"
        for reason, count in reasons.items():
            report += f"• {reason}: {count}\n"
    
    sections = stats.get("problem_sections", {})
    if sections:
        report += f"\n*Проблемные секции:*\n"
        for section, count in sections.items():
            report += f"• {section}: {count}\n"
    
    return report


def _export_csv(date_filter: str | None = None) -> tuple[bytes, str, int]:
    """
    Export feedback to CSV bytes.
    Returns: (csv_bytes, filename, record_count)
    """
    feedback_data = get_all_feedback(date_filter=date_filter)
    
    if not feedback_data:
        return None, None, 0
    
    clean_data = []
    for row in feedback_data:
        clean_data.append({
            "Дата": _format_date(row.get("timestamp", "")),
            "Оценка": _format_rating(row.get("rating", "")),
            "Причина": row.get("reason", "") or "-",
            "Комментарий": row.get("comment", "") or "-",
            "Вопрос": _truncate(row.get("question", ""), 150),
            "Ответ": _truncate(row.get("answer", ""), 200),
            "Раздел": row.get("section", "") or "-",
        })
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "Дата", "Оценка", "Причина", "Комментарий", "Вопрос", "Ответ", "Раздел"
    ], delimiter=";")
    writer.writeheader()
    writer.writerows(clean_data)
    
    csv_bytes = b'\xef\xbb\xbf' + output.getvalue().encode("utf-8")
    
    if date_filter:
        filename = f"feedback_{date_filter}.csv"
    else:
        filename = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return csv_bytes, filename, len(feedback_data)


# === Command handlers ===

@router.message(Command("admin"))
async def handle_admin_panel(message: Message) -> None:
    """Show admin panel with buttons."""
    uid = message.from_user.id
    un = message.from_user.username
    if not is_admin(uid, un) and not can_edit_prompt(uid, un):
        return  # Silently ignore for non-admins

    show_prompt = can_edit_prompt(uid, un)
    prompt_only = is_prompt_only_editor(uid, un)
    await message.answer(
        "🔐 *Админ-панель*\n\nВыберите действие:",
        reply_markup=get_admin_panel_kb(
            show_prompt=show_prompt,
            prompt_only=prompt_only,
        ),
        parse_mode="Markdown"
    )


@router.message(Command("report"))
async def handle_report(message: Message) -> None:
    """Handle /report command."""
    if not is_admin(message.from_user.id, message.from_user.username):
        return
    
    report = _build_report()
    await message.answer(report, parse_mode="Markdown")


@router.message(Command("export_feedback"))
async def handle_export_cmd(message: Message) -> None:
    """Handle /export_feedback command."""
    if not is_admin(message.from_user.id, message.from_user.username):
        return
    
    await message.answer(
        "📥 *Экспорт фидбека*\n\nВыберите период:",
        reply_markup=get_export_date_kb(),
        parse_mode="Markdown"
    )


# === Callback handlers ===

@router.callback_query(F.data == "admin:report")
async def cb_report(callback: CallbackQuery) -> None:
    """Handle report button."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    report = _build_report()
    await callback.message.answer(report, parse_mode="Markdown")


@router.callback_query(F.data == "admin:export")
async def cb_export_menu(callback: CallbackQuery) -> None:
    """Show export date selection."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "📥 *Экспорт фидбека*\n\nВыберите период:",
        reply_markup=get_export_date_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin:back")
async def cb_back(callback: CallbackQuery) -> None:
    """Back to admin panel."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    uid = callback.from_user.id
    un = callback.from_user.username
    show_prompt = can_edit_prompt(uid, un)
    prompt_only = is_prompt_only_editor(uid, un)
    await callback.message.edit_text(
        "🔐 *Админ-панель*\n\nВыберите действие:",
        reply_markup=get_admin_panel_kb(
            show_prompt=show_prompt,
            prompt_only=prompt_only,
        ),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin:export:today")
async def cb_export_today(callback: CallbackQuery) -> None:
    """Export today's feedback."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer("Готовлю экспорт...")
    
    today = datetime.now().strftime("%Y-%m-%d")
    csv_bytes, filename, count = _export_csv(date_filter=today)
    
    if not csv_bytes:
        await callback.message.answer(f"📊 Нет данных за сегодня ({today})")
        return
    
    file = BufferedInputFile(csv_bytes, filename=filename)
    await callback.message.answer_document(file, caption=f"📊 Фидбек за сегодня ({count} записей)")


@router.callback_query(F.data == "admin:export:yesterday")
async def cb_export_yesterday(callback: CallbackQuery) -> None:
    """Export yesterday's feedback."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer("Готовлю экспорт...")
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    csv_bytes, filename, count = _export_csv(date_filter=yesterday)
    
    if not csv_bytes:
        await callback.message.answer(f"📊 Нет данных за вчера ({yesterday})")
        return
    
    file = BufferedInputFile(csv_bytes, filename=filename)
    await callback.message.answer_document(file, caption=f"📊 Фидбек за вчера ({count} записей)")


@router.callback_query(F.data == "admin:export:all")
async def cb_export_all(callback: CallbackQuery) -> None:
    """Export all feedback."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer("Готовлю экспорт...")
    
    csv_bytes, filename, count = _export_csv()
    
    if not csv_bytes:
        await callback.message.answer("📊 Пока нет данных для экспорта.")
        return
    
    file = BufferedInputFile(csv_bytes, filename=filename)
    await callback.message.answer_document(file, caption=f"📊 Весь фидбек ({count} записей)")


@router.callback_query(F.data == "admin:users")
async def cb_users_menu(callback: CallbackQuery) -> None:
    """Меню: список в Telegram или выгрузка .txt."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "👤 Пользователи",
        reply_markup=get_admin_users_kb(),
    )


@router.callback_query(F.data == "admin:users:list")
async def cb_users_list(callback: CallbackQuery) -> None:
    """Показать список пользователей в Telegram (несколькими сообщениями при необходимости)."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    full = _format_users_list_for_telegram()
    chunks = _split_chunks(full, USERS_LIST_CHUNK)
    for i, ch in enumerate(chunks):
        prefix = f"Часть {i + 1}/{len(chunks)}\n\n" if len(chunks) > 1 else ""
        await callback.message.answer(prefix + ch)


@router.callback_query(F.data == "admin:users:download")
async def cb_users_download(callback: CallbackQuery) -> None:
    """Выгрузка списка пользователей в .txt."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer("Готовлю файл...")
    data = _users_txt_bytes()
    fname = f"bot_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file = BufferedInputFile(data, filename=fname)
    await callback.message.answer_document(
        file,
        caption="📋 Список пользователей (.txt)",
    )


# === Admin management callbacks ===

@router.callback_query(F.data == "admin:manage")
async def cb_manage_admins(callback: CallbackQuery) -> None:
    """Show admin management menu."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "👥 *Управление админами*\n\nВыберите действие:",
        reply_markup=get_admin_manage_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin:list")
async def cb_list_admins(callback: CallbackQuery) -> None:
    """List all admins."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    
    admins = get_admins()
    
    text = "👥 *Список админов:*\n\n"
    if Config.ADMIN_CHAT_IDS:
        text += "🆔 По ID из .env:\n"
        for aid in Config.ADMIN_CHAT_IDS:
            text += f"• {aid}\n"
    
    if Config.ADMIN_USERNAMES:
        text += f"\n📋 Из .env:\n"
        for u in Config.ADMIN_USERNAMES:
            text += f"• @{u}\n"
    
    if admins:
        text += f"\n📋 Добавленные:\n"
        for u in admins:
            text += f"• @{u}\n"
    elif not Config.ADMIN_USERNAMES:
        text += "\nДополнительных админов нет."
    
    await callback.message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "admin:add")
async def cb_add_admin_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt to add admin."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.answer(
        "➕ Введите @username нового админа:\n\n(или /cancel для отмены)"
    )
    await state.set_state(AdminStates.waiting_add_username)


@router.callback_query(F.data == "admin:remove")
async def cb_remove_admin_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt to remove admin."""
    if not is_admin(callback.from_user.id, callback.from_user.username):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    admins = get_admins()
    if not admins:
        await callback.answer("Нет админов для удаления", show_alert=True)
        return
    
    await callback.answer()
    text = "➖ Введите @username админа для удаления:\n\n"
    text += "Текущие админы:\n"
    for u in admins:
        text += f"• @{u}\n"
    text += "\n(или /cancel для отмены)"
    
    await callback.message.answer(text)
    await state.set_state(AdminStates.waiting_remove_username)


@router.message(AdminStates.waiting_add_username)
async def handle_add_admin(message: Message, state: FSMContext) -> None:
    """Handle adding new admin."""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return
    
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    
    username = message.text.strip().lstrip("@")
    
    if not username or len(username) < 3:
        await message.answer("❌ Неверный username. Попробуйте ещё раз:")
        return
    
    if add_admin(username, added_by=message.from_user.username):
        await message.answer(f"✅ Админ @{username} добавлен!")
    else:
        await message.answer(f"ℹ️ @{username} уже является админом.")
    
    await state.clear()


@router.message(AdminStates.waiting_remove_username)
async def handle_remove_admin(message: Message, state: FSMContext) -> None:
    """Handle removing admin."""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return
    
    if not is_admin(message.from_user.id, message.from_user.username):
        await state.clear()
        return
    
    username = message.text.strip().lstrip("@")
    
    if remove_admin(username):
        await message.answer(f"✅ Админ @{username} удалён!")
    else:
        await message.answer(f"❌ @{username} не найден в списке админов.")
    
    await state.clear()
