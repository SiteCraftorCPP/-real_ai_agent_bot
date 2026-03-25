"""Configuration loader from .env file."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Get the project root directory (parent of bot/)
project_root = Path(__file__).parent.parent

# Load environment variables from .env file
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)


def _parse_int_list(value: str) -> list[int]:
    """
    Parse comma-separated list of ints from env (e.g. "1,2,3").
    Silently drops invalid parts and zeros.
    """
    value = (value or "").strip()
    if not value:
        return []
    parts = [p.strip() for p in value.replace(" ", "").split(",") if p.strip()]
    out: list[int] = []
    for p in parts:
        try:
            n = int(p)
        except ValueError:
            continue
        if n != 0:
            out.append(n)
    return out


class Config:
    """Bot configuration."""
    
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
    # Optional: second (and more) admins by user_id/chat_id.
    # Example: ADMIN_CHAT_IDS=364593110,123456789
    _ADMIN_CHAT_IDS_PARSED: list[int] = _parse_int_list(os.getenv("ADMIN_CHAT_IDS", ""))
    ADMIN_CHAT_IDS: list[int] = (
        _ADMIN_CHAT_IDS_PARSED if _ADMIN_CHAT_IDS_PARSED else ([ADMIN_CHAT_ID] if ADMIN_CHAT_ID else [])
    )
    FEEDBACK_CHAT_ID: int = int(os.getenv("FEEDBACK_CHAT_ID", "0"))
    # Topic IDs for supergroup (0 if not using topics)
    FEEDBACK_TOPIC_ID: int = int(os.getenv("FEEDBACK_TOPIC_ID", "0"))
    LEADS_TOPIC_ID: int = int(os.getenv("LEADS_TOPIC_ID", "0"))
    # Список админов через запятую: @user1,@user2 или user1,user2
    ADMIN_USERNAMES: list[str] = [
        u.strip().lstrip("@").lower() 
        for u in os.getenv("ADMIN_USERNAMES", "").split(",") 
        if u.strip()
    ]
    # Кто может править CORE prompt через /admin → «Промпт GPT» (username без @, lower).
    # Если пусто — правят те же, что и обычные админы (ADMIN_USERNAMES + БД + главный ADMIN_CHAT_ID).
    PROMPT_ADMIN_USERNAMES: list[str] = [
        u.strip().lstrip("@").lower()
        for u in os.getenv("PROMPT_ADMIN_USERNAMES", "").split(",")
        if u.strip()
    ]
    LOGO_PATH: str = os.getenv("LOGO_PATH", "assets/logo.png")
    # PDF с ключевыми цифрами для онбординга (v1.3.5)
    KEY_FIGURES_PDF_PATH: str = os.getenv(
        "KEY_FIGURES_PDF_PATH",
        str(project_root / "Итоги_и_выводы_2025_Санкт_Петербург_Москва.pdf")
    )
    
    # ProxyAPI configuration (основной провайдер)
    PROXYAPI_API_KEY: str = os.getenv("PROXYAPI_API_KEY", "")
    PROXYAPI_BASE_URL: str = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1")
    PROXYAPI_MODEL: str = os.getenv("PROXYAPI_MODEL", "openai/gpt-5.1-chat-latest")
    PROXYAPI_MAX_TOKENS: int = int(os.getenv("PROXYAPI_MAX_TOKENS", "4000"))
    
    # OpenRouter configuration (опционально, для отката)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-5.1-chat-latest")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "Active Group Realty Bot")
    OPENROUTER_MAX_TOKENS: int = int(os.getenv("OPENROUTER_MAX_TOKENS", "1500"))
    
    # LLM Provider selection
    # Определение провайдера по умолчанию:
    # - Если задан PROXYAPI_API_KEY → proxyapi
    # - Если задан OPENROUTER_API_KEY → openrouter
    # - Иначе → proxyapi (по умолчанию)
    _default_provider = "proxyapi"
    if PROXYAPI_API_KEY.strip():
        _default_provider = "proxyapi"
    elif OPENROUTER_API_KEY.strip():
        _default_provider = "openrouter"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", _default_provider).lower()
    
    # Bot Configuration
    BOT_VERSION: str = os.getenv("BOT_VERSION", "1.3.5")
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    MAX_CONTEXT_MESSAGES: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "50"))
    
    # Feature Flags
    ENABLE_ANALYTICS: bool = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
    ENABLE_ESCALATION: bool = os.getenv("ENABLE_ESCALATION", "true").lower() == "true"
    ENABLE_MENU: bool = os.getenv("ENABLE_MENU", "true").lower() == "true"
    
    # Orchestrator Settings (v1.3.1)
    ESCALATION_ENABLED: bool = os.getenv("ESCALATION_ENABLED", "true").lower() == "true"
    ESCALATION_MIN_MESSAGES: int = int(os.getenv("ESCALATION_MIN_MESSAGES", "5"))
    ORCHESTRATOR_ENABLED: bool = os.getenv("ORCHESTRATOR_ENABLED", "true").lower() == "true"
    
    # Rate Limiting (v1.3.2)
    DAILY_MESSAGE_LIMIT: int = int(os.getenv("DAILY_MESSAGE_LIMIT", "40"))
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))
    
    # Escalation Limits (v1.3.2)
    ESCALATION_MAX_PER_DAY: int = int(os.getenv("ESCALATION_MAX_PER_DAY", "2"))
    ESCALATION_COOLDOWN_HOURS: int = int(os.getenv("ESCALATION_COOLDOWN_HOURS", "12"))
    # Escalation Button Settings (v1.3.3)
    ESCALATION_BUTTON_COOLDOWN_MESSAGES: int = int(os.getenv("ESCALATION_BUTTON_COOLDOWN_MESSAGES", "10"))
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration parameters."""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required in .env file")
