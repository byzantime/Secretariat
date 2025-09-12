import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DEBUG = os.environ.get("DEBUG", "False") == "True"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SECRET_KEY = os.environ["SECRET_KEY"]
    VERIFY_SSL = os.environ.get("VERIFY_SSL", "True").lower() == "true"
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    QUART_AUTH_COOKIE_SECURE = not DEBUG  # Allow insecure cookies in debug mode

    # Database URL - prefer individual components if available, fallback to DATABASE_URL
    DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
    DATABASE_PORT = os.environ.get("DATABASE_PORT", "5432")
    DATABASE_USER = os.environ.get("DATABASE_USER", "postgres")
    DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "src")
    DATABASE_URL = f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"

    ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

    # Basic agent configuration for skeleton
    AGENT_NAME = os.environ.get("AGENT_NAME", "Src Assistant")
