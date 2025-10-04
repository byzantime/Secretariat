import os

from dotenv import load_dotenv

load_dotenv()


def env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    value = os.environ.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


class Config:
    DEBUG = env_bool("DEBUG", False)
    LOG_LEVEL = os.environ["LOG_LEVEL"]
    SECRET_KEY = os.environ["SECRET_KEY"]
    VERIFY_SSL = env_bool("VERIFY_SSL", True)
    CREATE_TABLES_ON_STARTUP = env_bool("CREATE_TABLES_ON_STARTUP", False)
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    QUART_AUTH_COOKIE_SECURE = not DEBUG  # Allow insecure cookies in debug mode

    # Database URL - SQLite database in data directory
    DATA_DIR = os.environ.get("DATA_DIR", ".")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "secretariat")
    DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/{DATABASE_NAME}.db"

    # LLM Provider Configuration
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter")  # "openrouter" or "zen"

    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL")

    # OpenCode Zen Configuration
    ZEN_API_KEY = os.environ.get("ZEN_API_KEY", "")
    ZEN_MODEL = os.environ.get("ZEN_MODEL")

    BROWSER_USE_MODEL = os.environ.get("BROWSER_USE_MODEL", "")

    # Scheduling Configuration
    TIMEZONE = os.environ.get("TIMEZONE", "UTC")

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
    TELEGRAM_ALLOWED_USERS = os.environ.get("TELEGRAM_ALLOWED_USERS", "")

    # Memory System Configuration
    QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
    QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
    MEMORY_COLLECTION_NAME = os.environ.get("MEMORY_COLLECTION_NAME", "memories")

    # Browser Human Assistance
    BROWSER_USER_DATA_DIR = os.environ.get(
        "BROWSER_USER_DATA_DIR", f"{DATA_DIR}/browser_profile"
    )
    ASSISTANCE_LINK_EXPIRATION = int(
        os.environ.get("ASSISTANCE_LINK_EXPIRATION", "300")
    )  # 5 min
    ASSISTANCE_SECRET_KEY = os.environ.get("ASSISTANCE_SECRET_KEY", SECRET_KEY)

    # VNC Configuration
    VNC_DISPLAY = os.environ.get("VNC_DISPLAY", ":99")
    VNC_PORT = int(os.environ.get("VNC_PORT", "5900"))
    NOVNC_PORT = int(os.environ.get("NOVNC_PORT", "6080"))
