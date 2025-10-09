import os
from typing import Literal
from typing import Optional

from dotenv import dotenv_values
from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic_core import PydanticCustomError


class Settings(BaseModel):
    """Settings model for environment variables with validation and defaults."""

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

    # Timezone Configuration
    timezone: str = Field(default="UTC", description="Application timezone")

    # Hidden/Internal fields (not shown in form)
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Log level")
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for session encryption",
    )
    database_name: str = Field(default="secretariat", description="Database file name")
    data_dir: str = Field(
        default=".", description="Directory for storing database and persistent data"
    )

    @field_validator("openrouter_api_key")
    @classmethod
    def validate_openrouter_api_key(cls, v, info):
        """Validate OpenRouter API key is present when OpenRouter is selected."""
        if info.data.get("llm_provider") == "openrouter" and not v:
            raise PydanticCustomError(
                "missing_api_key",
                "OpenRouter API key is required when using OpenRouter",
            )
        return v

    @field_validator("zen_api_key")
    @classmethod
    def validate_zen_api_key(cls, v, info):
        """Validate Zen API key is present when Zen is selected."""
        if info.data.get("llm_provider") == "zen" and not v:
            raise PydanticCustomError(
                "missing_api_key",
                "Zen API key is required when using Opencode Zen",
            )
        return v

    def get_required_fields(self) -> list[str]:
        """Get list of required fields that must be set for the app to function."""
        required = []

        # Required fields based on provider
        if self.llm_provider == "openrouter":
            required.append("openrouter_api_key")
            required.append("openrouter_model")
        elif self.llm_provider == "zen":
            required.append("zen_api_key")
            required.append("zen_model")

        # Other required fields
        if self.telegram_bot_token:
            required.append("telegram_webhook_url")

        if self.qdrant_host:
            required.append("qdrant_api_key")

        return required

    def to_env_dict(self) -> dict[str, str]:
        """Convert settings to a dictionary suitable for writing to .env file."""
        env_dict = {}

        for field_name, field_info in self.__class__.model_fields.items():
            value = getattr(self, field_name)
            if value is not None:
                env_dict[field_name.upper()] = str(value)

        return env_dict

    @classmethod
    def from_env_file(cls, env_path: str = ".env", validate: bool = True) -> "Settings":
        """Load settings from .env file if it exists.

        Args:
            env_path: Path to .env file
            validate: Whether to validate the settings (False for initial setup)
        """
        if not os.path.exists(env_path):
            # Create settings without validation for initial setup
            if not validate:
                return cls.model_construct()
            raise FileNotFoundError(f".env file not found at {env_path}")

        # Load existing .env file into a dictionary
        env_values = dotenv_values(env_path)

        # Build settings from environment
        settings_dict = {}
        for field_name, field_info in cls.model_fields.items():
            env_name = field_name.upper()
            env_value = env_values.get(env_name)
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

        # Use model_construct to bypass validation if requested
        if not validate:
            return cls.model_construct(**settings_dict)

        return cls(**settings_dict)
