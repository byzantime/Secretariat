import os
from typing import Literal
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class Settings(BaseModel):
    """Settings model for environment variables with validation and defaults."""

    # Database Section
    database_name: str = Field(default="secretariat", description="Database file name")
    data_dir: str = Field(
        default=".", description="Directory for storing database and persistent data"
    )

    # LLM Provider Section
    llm_provider: Literal["openrouter", "zen"] = Field(
        default="zen", description="LLM provider to use"
    )
    openrouter_api_key: Optional[str] = Field(
        default=None, description="OpenRouter API key"
    )
    openrouter_model: str = Field(
        default="moonshotai/kimi-k2-0905", description="OpenRouter model to use"
    )
    zen_api_key: Optional[str] = Field(default=None, description="Zen API key")
    zen_model: str = Field(default="grok-code", description="Zen model to use")

    # Browser Configuration
    browser_use_model: str = Field(
        default="openai/o3", description="Model for browser automation"
    )
    browser_user_data_dir: str = Field(
        default="./data/browser_profile", description="Browser user data directory"
    )

    # Telegram Configuration
    telegram_bot_token: Optional[str] = Field(
        default=None, description="Telegram bot token"
    )
    telegram_webhook_url: Optional[str] = Field(
        default=None, description="Telegram webhook URL"
    )
    telegram_allowed_users: Optional[str] = Field(
        default=None, description="Comma-separated list of allowed Telegram user IDs"
    )

    # Memory System Configuration
    qdrant_host: Optional[str] = Field(default=None, description="Qdrant host URL")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    memory_collection_name: str = Field(
        default="memories", description="Memory collection name"
    )

    # Browser Human Assistance
    assistance_link_expiration: int = Field(
        default=300, description="Assistance link expiration time in seconds"
    )

    # VNC Configuration
    vnc_display: str = Field(default=":99", description="VNC display")
    vnc_port: int = Field(default=5900, description="VNC port")
    novnc_port: int = Field(default=6080, description="NoVNC port")

    # Browser Device Emulation
    browser_device: str = Field(default="pixel", description="Browser device emulation")

    # Hidden/Internal fields (not shown in form)
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Log level")
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for session encryption",
    )

    # Timezone Configuration
    timezone: str = Field(default="UTC", description="Application timezone")

    @model_validator(mode="after")
    def validate_provider_configs(self):
        """Validate that required provider-specific configurations are present."""
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OpenRouter API key is required when using OpenRouter")

        if self.llm_provider == "zen" and not self.zen_api_key:
            raise ValueError("Zen API key is required when using Opencode Zen")

        return self

    def get_required_fields(self) -> list[str]:
        """Get list of required fields that must be set for the app to function."""
        required = []

        # Required fields based on provider
        if self.llm_provider == "openrouter":
            required.append("openrouter_api_key")
        elif self.llm_provider == "zen":
            required.append("zen_api_key")

        # Other required fields
        if self.telegram_bot_token:
            required.append("telegram_webhook_url")

        if self.qdrant_host:
            required.append("qdrant_api_key")

        return required

    def to_env_dict(self) -> dict[str, str]:
        """Convert settings to a dictionary suitable for writing to .env file."""
        env_dict = {}

        for field_name, field_info in self.model_fields.items():
            value = getattr(self, field_name)
            if value is not None:
                env_dict[field_name.upper()] = str(value)

        return env_dict

    @classmethod
    def from_env_file(cls, env_path: str = ".env") -> "Settings":
        """Load settings from .env file if it exists."""
        if not os.path.exists(env_path):
            return cls()

        # Load existing .env file
        from dotenv import load_dotenv

        load_dotenv(env_path)

        # Build settings from environment
        settings_dict = {}
        for field_name, field_info in cls.model_fields.items():
            env_name = field_name.upper()
            env_value = os.environ.get(env_name)
            if env_value is not None:
                # Convert to appropriate type
                if field_info.annotation is int:
                    settings_dict[field_name] = int(env_value)
                elif field_info.annotation is bool:
                    settings_dict[field_name] = env_value.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )
                else:
                    settings_dict[field_name] = env_value

        return cls(**settings_dict)
