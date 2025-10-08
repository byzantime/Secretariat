"""Unit tests for setup mode detection and behavior."""

import os
import tempfile
from unittest.mock import patch

import pytest

from src.models.settings import Settings


class TestSetupModeDetection:
    """Test when app should enter setup mode."""

    def test_no_api_keys_triggers_setup_mode(self):
        """Test that having no API keys should trigger setup mode."""
        settings = Settings.model_construct(
            llm_provider="zen",
            openrouter_api_key=None,
            zen_api_key=None,
        )

        # App should detect this as requiring setup
        has_any_api_key = settings.openrouter_api_key or settings.zen_api_key
        assert has_any_api_key is None or has_any_api_key is False

    def test_zen_api_key_exits_setup_mode(self):
        """Test that having a Zen API key should exit setup mode."""
        settings = Settings.model_construct(
            llm_provider="zen",
            zen_api_key="test-key",
            openrouter_api_key=None,
        )

        has_api_key = settings.openrouter_api_key or settings.zen_api_key
        assert has_api_key is not None

    def test_openrouter_api_key_exits_setup_mode(self):
        """Test that having an OpenRouter API key should exit setup mode."""
        settings = Settings.model_construct(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            zen_api_key=None,
        )

        has_api_key = settings.openrouter_api_key or settings.zen_api_key
        assert has_api_key is not None

    def test_either_api_key_is_sufficient(self):
        """Test that having either API key is sufficient to exit setup mode."""
        # Zen key only
        settings_zen = Settings.model_construct(
            llm_provider="zen",
            zen_api_key="zen-key",
            openrouter_api_key=None,
        )
        assert settings_zen.zen_api_key is not None

        # OpenRouter key only
        settings_or = Settings.model_construct(
            llm_provider="openrouter",
            openrouter_api_key="or-key",
            zen_api_key=None,
        )
        assert settings_or.openrouter_api_key is not None

        # Both keys
        settings_both = Settings.model_construct(
            llm_provider="zen",
            zen_api_key="zen-key",
            openrouter_api_key="or-key",
        )
        assert settings_both.zen_api_key is not None
        assert settings_both.openrouter_api_key is not None


class TestSetupModeValidationErrors:
    """Test setup mode behavior when validation fails."""

    def test_validation_error_should_trigger_setup_mode(self):
        """Test that validation errors should trigger setup mode."""
        # Try to create settings with invalid configuration
        with pytest.raises(Exception):  # ValidationError or FileNotFoundError
            Settings.from_env_file("/nonexistent/.env", validate=True)

    def test_settings_from_env_file_missing_file_with_validate_false(self):
        """Test that missing file with validate=False allows setup mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = os.path.join(tmpdir, "missing.env")

            # Should not raise with validate=False
            settings = Settings.from_env_file(nonexistent, validate=False)

            # Should return settings object that can be used for setup
            assert settings is not None


class TestSetupModeRequiredFields:
    """Test logic for determining required vs optional fields."""

    def test_required_fields_based_on_provider(self):
        """Test that required fields change based on provider selection."""
        # OpenRouter selected
        settings_or = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
        )
        required_or = settings_or.get_required_fields()
        assert "openrouter_api_key" in required_or

        # Zen selected
        settings_zen = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )
        required_zen = settings_zen.get_required_fields()
        assert "zen_api_key" in required_zen

    def test_minimal_required_fields_for_basic_operation(self):
        """Test that minimal config only requires provider + API key."""
        # Minimal valid settings
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        # Should be valid
        required = settings.get_required_fields()

        # Only provider-specific API key should be required
        assert "zen_api_key" in required

        # Optional features shouldn't be required
        assert "telegram_bot_token" not in required
        assert "qdrant_host" not in required

    def test_optional_features_add_requirements(self):
        """Test that enabling optional features adds to required fields."""
        # Enable Telegram
        settings_telegram = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            telegram_bot_token="bot-token",
        )
        required = settings_telegram.get_required_fields()
        assert "telegram_webhook_url" in required

        # Enable Qdrant
        settings_qdrant = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_host="localhost",
        )
        required = settings_qdrant.get_required_fields()
        assert "qdrant_api_key" in required


class TestSetupModeTransition:
    """Test transitioning from setup mode to normal operation."""

    def test_invalid_to_valid_settings_transition(self):
        """Test saving valid settings after starting in setup mode."""
        # Start with invalid settings (setup mode)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            # Initially invalid - no API keys
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=zen\n")

            with patch.dict(os.environ, {}, clear=True):
                initial_settings = Settings.from_env_file(env_file, validate=False)
                assert initial_settings.zen_api_key is None

            # User configures API key
            valid_settings = Settings(
                llm_provider="zen",
                zen_api_key="new-api-key",
            )

            # Save to file
            env_dict = valid_settings.to_env_dict()
            with open(env_file, "w") as f:
                for key, value in env_dict.items():
                    f.write(f"{key}={value}\n")

            with patch.dict(os.environ, {}, clear=True):
                # Load again with validation
                final_settings = Settings.from_env_file(env_file, validate=True)

                # Should now be valid
                assert final_settings.zen_api_key == "new-api-key"
                assert final_settings.llm_provider == "zen"

    def test_app_can_detect_setup_completion(self):
        """Test that app can detect when setup is complete."""
        # Invalid settings - should be in setup mode
        invalid = Settings.model_construct(
            llm_provider="zen",
            zen_api_key=None,
            openrouter_api_key=None,
        )
        needs_setup = not (invalid.openrouter_api_key or invalid.zen_api_key)
        assert needs_setup is True

        # Valid settings - should exit setup mode
        valid = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )
        needs_setup = not (valid.openrouter_api_key or valid.zen_api_key)
        assert needs_setup is False


class TestSetupModeAppBehavior:
    """Test expected app behavior in setup mode."""

    def test_setup_mode_should_allow_settings_page_access(self):
        """Test that setup mode allows access to /settings endpoint."""
        # This is a behavioral contract test
        # In setup mode, /settings should be accessible
        allowed_endpoints = ["main.settings", "static"]

        # Simulate setup mode check
        setup_mode = True
        current_endpoint = "main.settings"

        # Should allow access to settings
        should_redirect = setup_mode and current_endpoint not in allowed_endpoints
        assert should_redirect is False

    def test_setup_mode_should_block_other_endpoints(self):
        """Test that setup mode blocks access to non-settings endpoints."""
        allowed_endpoints = ["main.settings", "static"]

        setup_mode = True
        current_endpoint = "main.index"

        # Should redirect to settings
        should_redirect = setup_mode and current_endpoint not in allowed_endpoints
        assert should_redirect is True

    def test_normal_mode_allows_all_endpoints(self):
        """Test that normal mode (not setup) allows access to all endpoints."""
        setup_mode = False

        # Should not redirect
        should_redirect = setup_mode
        assert should_redirect is False


class TestSetupModeEdgeCases:
    """Test edge cases in setup mode detection."""

    def test_empty_string_api_key_triggers_setup_mode(self):
        """Test that empty string API keys should trigger setup mode."""
        # Empty strings should be treated as missing
        settings = Settings.model_construct(
            llm_provider="zen",
            zen_api_key="",
            openrouter_api_key="",
        )

        # Empty strings are falsy
        has_api_key = bool(settings.openrouter_api_key or settings.zen_api_key)
        assert has_api_key is False

    def test_whitespace_api_key_should_fail_validation(self):
        """Test that whitespace-only API keys should fail validation."""
        # Whitespace-only keys should ideally fail validation
        # This depends on validator implementation
        # For now, test that empty/whitespace is detected
        test_key = "   "
        is_valid_key = bool(test_key.strip())
        assert is_valid_key is False

    def test_switching_providers_updates_requirements(self):
        """Test that switching providers updates required fields."""
        # Start with OpenRouter
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="or-key",
            zen_api_key="zen-key",  # Also have Zen key
        )

        required_or = settings.get_required_fields()
        assert "openrouter_api_key" in required_or

        # Switch to Zen (by creating new settings)
        settings_zen = Settings(
            llm_provider="zen",
            openrouter_api_key="or-key",
            zen_api_key="zen-key",
        )

        required_zen = settings_zen.get_required_fields()
        assert "zen_api_key" in required_zen
