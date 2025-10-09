import os

from dotenv import load_dotenv

from src.models.settings import Settings

# Load settings from .env file if it exists
# Use validate=False to allow loading settings without validation for initial setup
settings = Settings.from_env_file(validate=False)

# Load environment variables (will override .env file values)
load_dotenv()


def env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    value = os.environ.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


class Config:
    # Use settings from model, but allow environment variables to override
    DEBUG = env_bool("DEBUG", settings.debug)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", settings.log_level)
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        settings.secret_key,
    )
    QUART_AUTH_COOKIE_SECURE = not DEBUG  # Allow insecure cookies in debug mode

    # WTF Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No time limit on CSRF tokens

    # Database URL - SQLite database in data directory
    DATA_DIR = os.environ.get("DATA_DIR", settings.data_dir)
    DATABASE_NAME = os.environ.get("DATABASE_NAME", settings.database_name)
    DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/{DATABASE_NAME}.db"

    # LLM Provider Configuration
    LLM_PROVIDER = os.environ.get(
        "LLM_PROVIDER", settings.llm_provider
    )  # "openrouter" or "zen"

    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.environ.get(
        "OPENROUTER_API_KEY", settings.openrouter_api_key or ""
    )
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", settings.openrouter_model)

    # OpenCode Zen Configuration
    ZEN_API_KEY = os.environ.get("ZEN_API_KEY", settings.zen_api_key or "")
    ZEN_MODEL = os.environ.get("ZEN_MODEL", settings.zen_model)

    BROWSER_USE_MODEL = os.environ.get("BROWSER_USE_MODEL", settings.browser_use_model)

    # Scheduling Configuration
    TIMEZONE = os.environ.get("TIMEZONE", settings.timezone)

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN = os.environ.get(
        "TELEGRAM_BOT_TOKEN", settings.telegram_bot_token or ""
    )
    TELEGRAM_WEBHOOK_URL = os.environ.get(
        "TELEGRAM_WEBHOOK_URL", settings.telegram_webhook_url or ""
    )
    TELEGRAM_ALLOWED_USERS = os.environ.get(
        "TELEGRAM_ALLOWED_USERS", settings.telegram_allowed_users or ""
    )

    # Memory System Configuration
    QDRANT_HOST = os.environ.get("QDRANT_HOST", settings.qdrant_host or "localhost")
    QDRANT_PORT = int(os.environ.get("QDRANT_PORT", str(settings.qdrant_port)))
    QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", settings.qdrant_api_key)
    MEMORY_COLLECTION_NAME = os.environ.get(
        "MEMORY_COLLECTION_NAME", settings.memory_collection_name
    )

    # Browser Human Assistance
    BROWSER_USER_DATA_DIR = os.environ.get(
        "BROWSER_USER_DATA_DIR", settings.browser_user_data_dir
    )
    ASSISTANCE_LINK_EXPIRATION = int(
        os.environ.get(
            "ASSISTANCE_LINK_EXPIRATION", str(settings.assistance_link_expiration)
        )
    )  # 5 min

    # VNC Configuration
    VNC_DISPLAY = os.environ.get("VNC_DISPLAY", settings.vnc_display)
    VNC_PORT = int(os.environ.get("VNC_PORT", str(settings.vnc_port)))
    NOVNC_PORT = int(os.environ.get("NOVNC_PORT", str(settings.novnc_port)))

    # Browser Device Emulation
    BROWSER_DEVICE = os.environ.get("BROWSER_DEVICE", settings.browser_device)


def save_settings_to_env(settings: Settings) -> None:
    """Save settings to .env file in project root."""
    env_path = os.path.join(os.getcwd(), ".env")

    # Convert settings to env format
    env_dict = settings.to_env_dict()

    # Write to .env file
    with open(env_path, "w") as f:
        for key, value in env_dict.items():
            f.write(f"{key}={value}\n")
