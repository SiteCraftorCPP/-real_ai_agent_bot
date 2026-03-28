"""SQLite database for feedback storage and analytics."""
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    """Initialize database tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            timestamp TEXT NOT NULL,
            rating TEXT NOT NULL,
            reason TEXT,
            comment TEXT,
            question TEXT,
            answer TEXT,
            section TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            added_by TEXT,
            added_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            username TEXT,
            section TEXT NOT NULL,
            started_at TEXT NOT NULL,
            messages TEXT DEFAULT '[]'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)
    """)
    # v1.3.2: User slots (persistent memory)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_slots (
            user_id INTEGER PRIMARY KEY,
            city TEXT,
            budget TEXT,
            object_type TEXT,
            goal TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    # v1.3.2: Escalation tracking (persistent across restarts)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_escalations (
            user_id INTEGER PRIMARY KEY,
            daily_count INTEGER DEFAULT 0,
            daily_reset_at TEXT NOT NULL,
            last_escalation_at TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    # v1.3.5: One-time onboarding tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_onboarding (
            user_id INTEGER PRIMARY KEY,
            onboarding_shown_at TEXT NOT NULL
        )
    """)

    # Known forum topic ids (message_thread_id) per chat
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_forum_threads (
            chat_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, thread_id)
        )
    """)
    # Уникальные пользователи бота (для админской статистики)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
    """)
    conn.commit()


def save_feedback(
    user_id: int,
    username: Optional[str],
    rating: str,
    reason: Optional[str] = None,
    comment: Optional[str] = None,
    question: Optional[str] = None,
    answer: Optional[str] = None,
    section: Optional[str] = None
) -> int:
    """
    Save feedback to database.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username
        rating: 'positive' or 'negative'
        reason: Reason for negative feedback
        comment: User comment
        question: User's question that was answered
        answer: Bot's answer
        section: Selected menu section
        
    Returns:
        ID of inserted record
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO feedback (user_id, username, timestamp, rating, reason, comment, question, answer, section)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            datetime.now().isoformat(),
            rating,
            reason,
            comment,
            question,
            answer,
            section
        ))
        conn.commit()
        feedback_id = cursor.lastrowid
        logger.info(f"Saved feedback #{feedback_id}: {rating} from user {user_id}")
        return feedback_id
    finally:
        conn.close()


def get_stats() -> dict:
    """
    Get feedback statistics.
    
    Returns:
        Dict with stats: total, positive, negative, reasons breakdown, sections breakdown
    """
    conn = get_connection()
    try:
        # Total counts
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        positive = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='positive'").fetchone()[0]
        negative = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='negative'").fetchone()[0]
        
        # Reasons breakdown (for negative)
        reasons_rows = conn.execute("""
            SELECT reason, COUNT(*) as cnt 
            FROM feedback 
            WHERE rating='negative' AND reason IS NOT NULL
            GROUP BY reason 
            ORDER BY cnt DESC
        """).fetchall()
        reasons = {row['reason']: row['cnt'] for row in reasons_rows}
        
        # Sections breakdown (negative only)
        sections_rows = conn.execute("""
            SELECT section, COUNT(*) as cnt 
            FROM feedback 
            WHERE rating='negative' AND section IS NOT NULL AND section != ''
            GROUP BY section 
            ORDER BY cnt DESC
            LIMIT 5
        """).fetchall()
        problem_sections = {row['section']: row['cnt'] for row in sections_rows}
        
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "reasons": reasons,
            "problem_sections": problem_sections
        }
    finally:
        conn.close()


def get_all_feedback(limit: int = 1000, date_filter: Optional[str] = None) -> list[dict]:
    """
    Get all feedback records for export.
    
    Args:
        limit: Maximum number of records
        date_filter: Filter by date (YYYY-MM-DD format)
        
    Returns:
        List of feedback records as dicts
    """
    conn = get_connection()
    try:
        if date_filter:
            # Filter by date (timestamp starts with date)
            rows = conn.execute("""
                SELECT * FROM feedback 
                WHERE timestamp LIKE ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (f"{date_filter}%", limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM feedback 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# === Admin management ===

def add_admin(username: str, added_by: str | None = None) -> bool:
    """
    Add admin by username.
    Returns True if added, False if already exists.
    """
    username = username.lstrip("@").lower()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO admins (username, added_by, added_at)
            VALUES (?, ?, ?)
        """, (username, added_by, datetime.now().isoformat()))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def remove_admin(username: str) -> bool:
    """
    Remove admin by username.
    Returns True if removed, False if not found.
    """
    username = username.lstrip("@").lower()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM admins WHERE username = ?", (username,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_admins() -> list[str]:
    """Get list of admin usernames."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT username FROM admins").fetchall()
        return [row["username"] for row in rows]
    finally:
        conn.close()


def is_db_admin(username: str | None) -> bool:
    """Check if username is in admins table."""
    if not username:
        return False
    username = username.lstrip("@").lower()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM admins WHERE username = ?", (username,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# === Session management ===

def start_new_session(
    user_id: int,
    username: Optional[str],
    section: str
) -> str:
    """
    Start a new session for user.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username
        section: Section name (rent, deal, market, docs_taxes, question)
        
    Returns:
        session_id (timestamp-based unique ID)
    """
    session_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    started_at = datetime.now().isoformat()
    
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO sessions (session_id, user_id, username, section, started_at, messages)
            VALUES (?, ?, ?, ?, ?, '[]')
        """, (session_id, user_id, username, section, started_at))
        conn.commit()
        logger.info(f"Started new session {session_id} for user {user_id} in section {section}")
        return session_id
    finally:
        conn.close()


def save_session_message(
    session_id: str,
    role: str,
    text: str
) -> None:
    """
    Save a message to the session history.
    
    Args:
        session_id: Session ID
        role: "U" for user, "B" for bot
        text: Message text
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    conn = get_connection()
    try:
        # Get current messages
        row = conn.execute(
            "SELECT messages FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        
        if row:
            messages = json.loads(row["messages"])
            messages.append({
                "role": role,
                "text": text,
                "timestamp": timestamp
            })
            
            conn.execute(
                "UPDATE sessions SET messages = ? WHERE session_id = ?",
                (json.dumps(messages, ensure_ascii=False), session_id)
            )
            conn.commit()
            logger.debug(f"Saved message to session {session_id}: {role}")
    finally:
        conn.close()


def get_session_history(session_id: str) -> list[dict]:
    """
    Get all messages from a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        List of message dicts with role, text, timestamp
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT messages FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        
        if row:
            return json.loads(row["messages"])
        return []
    finally:
        conn.close()


def get_session_info(session_id: str) -> Optional[dict]:
    """
    Get session metadata.
    
    Args:
        session_id: Session ID
        
    Returns:
        Dict with session info or None if not found
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT session_id, user_id, username, section, started_at FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_user_current_session(user_id: int) -> Optional[str]:
    """
    Get the most recent session_id for a user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        session_id or None if no session exists
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        
        if row:
            return row["session_id"]
        return None
    finally:
        conn.close()


# === User slots management (v1.3.2) ===

def load_user_slots(user_id: int) -> dict:
    """
    Load user slots from database.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Dict with city, budget, object_type, goal (None if not set)
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT city, budget, object_type, goal FROM user_slots WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if row:
            return {
                "city": row["city"],
                "budget": row["budget"],
                "object_type": row["object_type"],
                "goal": row["goal"]
            }
        return {
            "city": None,
            "budget": None,
            "object_type": None,
            "goal": None
        }
    finally:
        conn.close()


def save_user_slots(user_id: int, slots: dict) -> None:
    """
    Save user slots to database.
    
    Args:
        user_id: Telegram user ID
        slots: Dict with city, budget, object_type, goal
    """
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_slots (user_id, city, budget, object_type, goal, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            slots.get("city"),
            slots.get("budget"),
            slots.get("object_type"),
            slots.get("goal"),
            datetime.now().isoformat()
        ))
        conn.commit()
        logger.debug(f"Saved slots for user {user_id}")
    finally:
        conn.close()


def update_user_slot(user_id: int, slot_name: str, value: str) -> None:
    """
    Update a single slot for user.
    
    Args:
        user_id: Telegram user ID
        slot_name: Slot name (city, budget, object_type, goal)
        value: Value to set
    """
    if slot_name not in ["city", "budget", "object_type", "goal"]:
        logger.warning(f"Invalid slot name: {slot_name}")
        return
    
    conn = get_connection()
    try:
        # Check if user exists
        row = conn.execute(
            "SELECT user_id FROM user_slots WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if row:
            # Update existing
            conn.execute(
                f"UPDATE user_slots SET {slot_name} = ?, updated_at = ? WHERE user_id = ?",
                (value, datetime.now().isoformat(), user_id)
            )
        else:
            # Insert new
            conn.execute(
                f"""INSERT INTO user_slots (user_id, {slot_name}, updated_at)
                    VALUES (?, ?, ?)""",
                (user_id, value, datetime.now().isoformat())
            )
        conn.commit()
        logger.debug(f"Updated slot {slot_name} for user {user_id}")
    finally:
        conn.close()


# === Escalation tracking (v1.3.2) ===

def load_user_escalation_data(user_id: int) -> dict:
    """
    Load escalation data from database.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Dict with daily_count, daily_reset_at, last_escalation_at
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT daily_count, daily_reset_at, last_escalation_at FROM user_escalations WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if row:
            return {
                "daily_count": row["daily_count"],
                "daily_reset_at": row["daily_reset_at"],
                "last_escalation_at": row["last_escalation_at"]
            }
        return {
            "daily_count": 0,
            "daily_reset_at": datetime.now().strftime("%Y-%m-%d"),
            "last_escalation_at": None
        }
    finally:
        conn.close()


def save_user_escalation_data(user_id: int, data: dict) -> None:
    """
    Save escalation data to database.
    
    Args:
        user_id: Telegram user ID
        data: Dict with daily_count, daily_reset_at, last_escalation_at
    """
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_escalations 
            (user_id, daily_count, daily_reset_at, last_escalation_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("daily_count", 0),
            data.get("daily_reset_at", datetime.now().strftime("%Y-%m-%d")),
            data.get("last_escalation_at"),
            datetime.now().isoformat()
        ))
        conn.commit()
        logger.debug(f"Saved escalation data for user {user_id}")
    finally:
        conn.close()


def increment_user_escalation(user_id: int) -> dict:
    """
    Increment escalation counter for user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Updated escalation data
    """
    data = load_user_escalation_data(user_id)
    
    # Reset if new day
    today = datetime.now().strftime("%Y-%m-%d")
    if data["daily_reset_at"] != today:
        data["daily_count"] = 0
        data["daily_reset_at"] = today
    
    # Increment and set last escalation time
    data["daily_count"] += 1
    data["last_escalation_at"] = datetime.now().isoformat()
    
    save_user_escalation_data(user_id, data)
    return data


# === Onboarding tracking (v1.3.5) ===

def has_seen_onboarding(user_id: int) -> bool:
    """
    Check if user has already seen the one-time onboarding.

    Args:
        user_id: Telegram user ID

    Returns:
        True if user has seen onboarding, False otherwise
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM user_onboarding WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_onboarding_shown(user_id: int) -> None:
    """
    Mark that user has seen the one-time onboarding.

    Args:
        user_id: Telegram user ID
    """
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_onboarding (user_id, onboarding_shown_at)
            VALUES (?, ?)
        """, (user_id, datetime.now().isoformat()))
        conn.commit()
        logger.debug(f"Marked onboarding shown for user {user_id}")
    finally:
        conn.close()


def upsert_forum_thread(chat_id: int, thread_id: int) -> None:
    """Remember forum topic (message_thread_id) for later /chatids listing."""
    if not chat_id or not thread_id:
        return
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO known_forum_threads (chat_id, thread_id, last_seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, thread_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
            """,
            (chat_id, thread_id, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_forum_threads(chat_id: int) -> list[dict]:
    """Return known forum topic (thread_id) records for a chat."""
    if not chat_id:
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT thread_id, last_seen_at
            FROM known_forum_threads
            WHERE chat_id = ?
            ORDER BY thread_id ASC
            """,
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_bot_user(user_id: int, username: Optional[str]) -> None:
    """
    Записать/обновить пользователя: при первом заходе — first_seen_at,
    при каждом контакте — last_seen_at и актуальный username.
    """
    now = datetime.now().isoformat()
    un = (username or "").strip() or None
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO bot_users (user_id, username, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, bot_users.username),
                last_seen_at = excluded.last_seen_at
            """,
            (user_id, un, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_bot_users_stats() -> dict:
    """Всего пользователей и «новые» по first_seen_at за 24ч и 7 дней."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        new_24h = conn.execute(
            "SELECT COUNT(*) FROM bot_users WHERE first_seen_at >= ?",
            (day_ago,),
        ).fetchone()[0]
        new_7d = conn.execute(
            "SELECT COUNT(*) FROM bot_users WHERE first_seen_at >= ?",
            (week_ago,),
        ).fetchone()[0]
        return {
            "total": total,
            "new_24h": new_24h,
            "new_7d": new_7d,
        }
    finally:
        conn.close()


def get_all_bot_users() -> list[dict]:
    """Все пользователи, сначала недавно добавленные."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT user_id, username, first_seen_at, last_seen_at
            FROM bot_users
            ORDER BY first_seen_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
