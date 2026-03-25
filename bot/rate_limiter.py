"""Rate limiting system for user messages (v1.3.2)."""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple
from bot.config import Config

logger = logging.getLogger(__name__)

# In-memory cache for rate limits (user_id -> data)
_rate_limit_cache = {}


class RateLimitResult:
    """Result of rate limit check."""
    
    def __init__(self, allowed: bool, message: Optional[str] = None, retry_after: Optional[int] = None):
        self.allowed = allowed
        self.message = message
        self.retry_after = retry_after  # seconds until user can send again


def _get_day_key() -> str:
    """Get current day key for daily limits (YYYY-MM-DD)."""
    return datetime.now().strftime("%Y-%m-%d")


def _get_user_data(user_id: int) -> dict:
    """Get or initialize user rate limit data."""
    if user_id not in _rate_limit_cache:
        _rate_limit_cache[user_id] = {
            "daily_count": 0,
            "daily_reset_at": _get_day_key(),
            "last_message_times": []  # List of timestamps for per-minute tracking
        }
    return _rate_limit_cache[user_id]


def _reset_daily_if_needed(user_data: dict) -> None:
    """Reset daily counter if it's a new day."""
    current_day = _get_day_key()
    if user_data["daily_reset_at"] != current_day:
        user_data["daily_count"] = 0
        user_data["daily_reset_at"] = current_day
        logger.info(f"Daily rate limit reset for new day: {current_day}")


def _clean_old_timestamps(user_data: dict) -> None:
    """Remove timestamps older than 1 minute."""
    now = time.time()
    cutoff = now - 60  # 60 seconds ago
    user_data["last_message_times"] = [
        ts for ts in user_data["last_message_times"] 
        if ts > cutoff
    ]


def check_rate_limit(user_id: int) -> RateLimitResult:
    """
    Check if user can send a message based on rate limits.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        RateLimitResult with allowed status and optional message
    """
    user_data = _get_user_data(user_id)
    
    # Reset daily counter if new day
    _reset_daily_if_needed(user_data)
    
    # Check daily limit (40 messages per day)
    if user_data["daily_count"] >= Config.DAILY_MESSAGE_LIMIT:
        logger.warning(f"User {user_id} exceeded daily message limit ({Config.DAILY_MESSAGE_LIMIT})")
        return RateLimitResult(
            allowed=False,
            message="Вы достигли дневного лимита сообщений. Попробуйте завтра или обратитесь к специалисту."
        )
    
    # Clean old timestamps
    _clean_old_timestamps(user_data)
    
    # Check per-minute limit (5 messages per minute)
    if len(user_data["last_message_times"]) >= Config.RATE_LIMIT_PER_MINUTE:
        logger.warning(f"User {user_id} exceeded per-minute rate limit ({Config.RATE_LIMIT_PER_MINUTE})")
        # Calculate when they can send again
        oldest_message = min(user_data["last_message_times"])
        retry_after = int(60 - (time.time() - oldest_message)) + 1
        return RateLimitResult(
            allowed=False,
            message="Пожалуйста, подождите немного перед следующим сообщением.",
            retry_after=retry_after
        )
    
    # Allowed - return success
    return RateLimitResult(allowed=True)


def record_message(user_id: int) -> None:
    """
    Record that user sent a message (increment counters).
    
    Args:
        user_id: Telegram user ID
    """
    user_data = _get_user_data(user_id)
    
    # Reset daily if needed
    _reset_daily_if_needed(user_data)
    
    # Increment daily counter
    user_data["daily_count"] += 1
    
    # Add timestamp for per-minute tracking
    user_data["last_message_times"].append(time.time())
    
    # Clean old timestamps
    _clean_old_timestamps(user_data)
    
    logger.debug(f"User {user_id} message recorded: daily={user_data['daily_count']}/{Config.DAILY_MESSAGE_LIMIT}, "
                f"per_minute={len(user_data['last_message_times'])}/{Config.RATE_LIMIT_PER_MINUTE}")


def get_user_stats(user_id: int) -> dict:
    """
    Get current rate limit stats for user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Dict with daily_count, daily_limit, per_minute_count, per_minute_limit
    """
    user_data = _get_user_data(user_id)
    _reset_daily_if_needed(user_data)
    _clean_old_timestamps(user_data)
    
    return {
        "daily_count": user_data["daily_count"],
        "daily_limit": Config.DAILY_MESSAGE_LIMIT,
        "per_minute_count": len(user_data["last_message_times"]),
        "per_minute_limit": Config.RATE_LIMIT_PER_MINUTE,
        "daily_reset_at": user_data["daily_reset_at"]
    }


def reset_user_limits(user_id: int) -> None:
    """
    Reset all rate limits for a user (admin command).
    
    Args:
        user_id: Telegram user ID
    """
    if user_id in _rate_limit_cache:
        del _rate_limit_cache[user_id]
        logger.info(f"Rate limits reset for user {user_id}")
