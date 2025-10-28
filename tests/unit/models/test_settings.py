"""Unit tests for Settings model validation and behavior."""

import pytest
from pydantic import ValidationError

from src.models.settings import Settings


class TestSettingsDefaults:
    """Test Settings model default values."""

    def test_settings_has_sensible_defaults(self):
        """Test that Settings can be created with defaults only."""
        # Use model_construct to bypass validation for this test
        settings = Settings.model_construct()

        # LLM defaults
        assert settings.llm_provider == "zen"
        assert settings.openrouter_model == "moonshotai/kimi-k2-0905"
        assert settings.zen_model == "grok-code"

        # Browser defaults
        assert settings.browser_use_model == "openai/o3"
        assert settings.browser_user_data_dir == "./data/browser_profile"

        # Memory defaults
        assert settings.qdrant_port == 6333
        assert settings.memory_collection_name == "memories"

        # VNC defaults
        assert settings.vnc_display == ":99"
        assert settings.vnc_port == 5900
        assert settings.novnc_port == 6080

        # Other defaults
        assert settings.timezone == "UTC"
        assert settings.assistance_link_expiration == 300
        assert settings.debug is False
        assert settings.log_level == "INFO"

    def test_optional_fields_default_to_none(self):
        """Test that optional fields default to None."""
        settings = Settings.model_construct()

        assert settings.openrouter_api_key is None
        assert settings.zen_api_key is None
        assert settings.telegram_bot_token is None
        assert settings.telegram_webhook_url is None
        assert settings.telegram_allowed_users is None
        assert settings.qdrant_host is None
        assert settings.qdrant_api_key is None


class TestSettingsProviderValidation:
    """Test provider-specific validation logic."""

    def test_openrouter_requires_api_key(self):
        """Test that selecting OpenRouter requires an API key."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                llm_provider="openrouter",
                openrouter_api_key=None,
            )

        # Check that the error is about the missing API key
        errors = exc_info.value.errors()
        assert any("OpenRouter API key is required" in str(e["msg"]) for e in errors)

    def test_openrouter_with_api_key_succeeds(self):
        """Test that OpenRouter with API key validates successfully."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key-123",
        )

        assert settings.llm_provider == "openrouter"
        assert settings.openrouter_api_key == "test-key-123"

    def test_zen_requires_api_key(self):
        """Test that selecting Zen requires an API key."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                llm_provider="zen",
                zen_api_key=None,
            )

        errors = exc_info.value.errors()
        assert any("Zen API key is required" in str(e["msg"]) for e in errors)

    def test_zen_with_api_key_succeeds(self):
        """Test that Zen with API key validates successfully."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-zen-key",
        )

        assert settings.llm_provider == "zen"
        assert settings.zen_api_key == "test-zen-key"

    def test_can_have_both_api_keys(self):
        """Test that having both API keys is valid (allows switching)."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="zen-key",
            openrouter_api_key="openrouter-key",
        )

        assert settings.zen_api_key == "zen-key"
        assert settings.openrouter_api_key == "openrouter-key"

    def test_provider_must_be_valid_literal(self):
        """Test that llm_provider only accepts valid values."""
        with pytest.raises(ValidationError):
            Settings(
                llm_provider="invalid-provider",
                zen_api_key="test-key",
            )


class TestSettingsFieldTypes:
    """Test that field types are validated correctly."""

    def test_integer_fields_validated(self):
        """Test that integer fields require valid integers."""
        with pytest.raises(ValidationError):
            Settings(
                llm_provider="zen",
                zen_api_key="test-key",
                qdrant_port="not-a-number",
            )

    def test_integer_fields_accept_integers(self):
        """Test that integer fields accept valid integers."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_port=6333,
            vnc_port=5900,
            novnc_port=6080,
            assistance_link_expiration=600,
        )

        assert settings.qdrant_port == 6333
        assert settings.vnc_port == 5900
        assert settings.novnc_port == 6080
        assert settings.assistance_link_expiration == 600

    def test_boolean_fields_validated(self):
        """Test that boolean fields work correctly."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            debug=True,
        )

        assert settings.debug is True

    def test_string_fields_accept_strings(self):
        """Test that string fields accept strings."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            timezone="America/New_York",
            vnc_display=":1",
        )

        assert settings.timezone == "America/New_York"
        assert settings.vnc_display == ":1"


class TestSettingsRequiredFieldsLogic:
    """Test the get_required_fields() method logic."""

    def test_openrouter_required_fields(self):
        """Test required fields when using OpenRouter."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
        )

        required = settings.get_required_fields()
        assert "openrouter_api_key" in required

    def test_zen_required_fields(self):
        """Test required fields when using Zen."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        required = settings.get_required_fields()
        assert "zen_api_key" in required

    def test_telegram_requires_webhook_when_token_set(self):
        """Test that setting telegram_bot_token adds webhook to required fields."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            telegram_bot_token="bot-token",
        )

        required = settings.get_required_fields()
        assert "telegram_webhook_url" in required

    def test_telegram_no_requirements_when_not_configured(self):
        """Test that telegram fields are not required when not configured."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        required = settings.get_required_fields()
        assert "telegram_webhook_url" not in required

    def test_qdrant_requires_api_key_when_host_set(self):
        """Test that setting qdrant_host adds api_key to required fields."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_host="localhost",
        )

        required = settings.get_required_fields()
        assert "qdrant_api_key" in required

    def test_qdrant_no_requirements_when_not_configured(self):
        """Test that qdrant fields are not required when not configured."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        required = settings.get_required_fields()
        assert "qdrant_api_key" not in required


class TestSettingsOptionalBehavior:
    """Test behavior of optional fields."""

    def test_can_create_minimal_settings(self):
        """Test that minimal valid settings can be created."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        # Should have provider and key
        assert settings.llm_provider == "zen"
        assert settings.zen_api_key == "test-key"

        # Optional fields should be None
        assert settings.telegram_bot_token is None
        assert settings.qdrant_host is None

    def test_can_override_all_defaults(self):
        """Test that all default values can be overridden."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="custom-model",
            zen_model="custom-zen",
            browser_use_model="custom-browser",
            browser_user_data_dir="/custom/path",
            timezone="Europe/London",
            vnc_display=":100",
            vnc_port=5901,
            novnc_port=6081,
            qdrant_port=6334,
            memory_collection_name="custom_memories",
            assistance_link_expiration=600,
            debug=True,
            log_level="DEBUG",
            secret_key="custom-secret",
            database_name="custom_db",
            data_dir="/custom/data",
        )

        # Verify overrides work
        assert settings.openrouter_model == "custom-model"
        assert settings.timezone == "Europe/London"
        assert settings.vnc_port == 5901
        assert settings.debug is True
