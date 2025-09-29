import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DEBUG = os.environ.get("DEBUG", "False") == "True"
    LOG_LEVEL = os.environ["LOG_LEVEL"]
    SECRET_KEY = os.environ["SECRET_KEY"]
    VERIFY_SSL = os.environ.get("VERIFY_SSL", "True").lower() == "true"
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    QUART_AUTH_COOKIE_SECURE = not DEBUG  # Allow insecure cookies in debug mode

    # Database URL - SQLite database in project root
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "secretariat")
    DATABASE_URL = f"sqlite+aiosqlite:///./{DATABASE_NAME}.db"

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
