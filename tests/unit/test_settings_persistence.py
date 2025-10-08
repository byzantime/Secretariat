"""Unit tests for Settings persistence (to_env_dict, from_env_file)."""

import os
import tempfile
from unittest.mock import patch

import pytest

from src.models.settings import Settings


class TestSettingsToEnvDict:
    """Test Settings.to_env_dict() serialization."""

    def test_to_env_dict_converts_field_names_to_uppercase(self):
        """Test that field names are converted to uppercase for env vars."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        env_dict = settings.to_env_dict()

        assert "LLM_PROVIDER" in env_dict
        assert "ZEN_API_KEY" in env_dict
        assert "llm_provider" not in env_dict

    def test_to_env_dict_excludes_none_values(self):
        """Test that None values are excluded from env dict."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            # telegram fields left as None
        )

        env_dict = settings.to_env_dict()

        # Should not contain None values
        assert "TELEGRAM_BOT_TOKEN" not in env_dict
        assert "TELEGRAM_WEBHOOK_URL" not in env_dict
        assert "QDRANT_HOST" not in env_dict

    def test_to_env_dict_includes_all_non_none_values(self):
        """Test that all non-None values are included."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="custom-model",
            timezone="America/New_York",
            debug=True,
        )

        env_dict = settings.to_env_dict()

        assert env_dict["LLM_PROVIDER"] == "openrouter"
        assert env_dict["OPENROUTER_API_KEY"] == "test-key"
        assert env_dict["OPENROUTER_MODEL"] == "custom-model"
        assert env_dict["TIMEZONE"] == "America/New_York"
        assert env_dict["DEBUG"] == "True"

    def test_to_env_dict_converts_values_to_strings(self):
        """Test that all values are converted to strings."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_port=6333,
            debug=True,
            assistance_link_expiration=600,
        )

        env_dict = settings.to_env_dict()

        # All values should be strings
        assert isinstance(env_dict["QDRANT_PORT"], str)
        assert env_dict["QDRANT_PORT"] == "6333"
        assert isinstance(env_dict["DEBUG"], str)
        assert env_dict["DEBUG"] == "True"
        assert isinstance(env_dict["ASSISTANCE_LINK_EXPIRATION"], str)
        assert env_dict["ASSISTANCE_LINK_EXPIRATION"] == "600"


class TestSettingsFromEnvFile:
    """Test Settings.from_env_file() loading."""

    def test_from_env_file_missing_file_with_validate_false(self):
        """Test that missing file with validate=False returns empty settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = os.path.join(tmpdir, "nonexistent.env")

            settings = Settings.from_env_file(nonexistent, validate=False)

            # Should return settings with defaults (using model_construct)
            assert settings is not None
            assert settings.llm_provider == "zen"

    def test_from_env_file_missing_file_with_validate_true_raises(self):
        """Test that missing file with validate=True raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = os.path.join(tmpdir, "nonexistent.env")

            with pytest.raises(FileNotFoundError):
                Settings.from_env_file(nonexistent, validate=True)

    def test_from_env_file_loads_valid_settings(self):
        """Test loading valid settings from .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            # Write a valid .env file
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=openrouter\n")
                f.write("OPENROUTER_API_KEY=test-key-123\n")
                f.write("OPENROUTER_MODEL=custom-model\n")
                f.write("TIMEZONE=Europe/London\n")

            settings = Settings.from_env_file(env_file, validate=True)

            assert settings.llm_provider == "openrouter"
            assert settings.openrouter_api_key == "test-key-123"
            assert settings.openrouter_model == "custom-model"
            assert settings.timezone == "Europe/London"

    def test_from_env_file_parses_integers(self):
        """Test that integer fields are parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=zen\n")
                f.write("ZEN_API_KEY=test-key\n")
                f.write("QDRANT_PORT=6334\n")
                f.write("VNC_PORT=5901\n")
                f.write("ASSISTANCE_LINK_EXPIRATION=300\n")

            settings = Settings.from_env_file(env_file, validate=True)

            assert settings.qdrant_port == 6334
            assert settings.vnc_port == 5901
            assert settings.assistance_link_expiration == 300
            assert isinstance(settings.qdrant_port, int)

    def test_from_env_file_parses_booleans(self):
        """Test that boolean fields are parsed correctly."""
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
        ]

        for bool_str, expected in test_cases:
            with tempfile.TemporaryDirectory() as tmpdir:
                env_file = os.path.join(tmpdir, ".env")

                with open(env_file, "w") as f:
                    f.write("LLM_PROVIDER=zen\n")
                    f.write("ZEN_API_KEY=test-key\n")
                    f.write(f"DEBUG={bool_str}\n")

                # Mock environment to isolate test
                with patch.dict(os.environ, {}, clear=True):
                    settings = Settings.from_env_file(env_file, validate=True)
                    assert settings.debug is expected, f"Failed for {bool_str}"

    def test_from_env_file_handles_optional_fields(self):
        """Test that optional fields can be omitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            # Minimal valid config
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=zen\n")
                f.write("ZEN_API_KEY=test-key\n")

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env_file(env_file, validate=True)

                # Optional fields should be None or defaults
                assert settings.telegram_bot_token is None
                assert settings.qdrant_host is None
                assert settings.timezone == "UTC"  # default

    def test_from_env_file_with_validate_false_allows_invalid(self):
        """Test that validate=False allows invalid settings to load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            # Invalid: OpenRouter selected but no API key
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=openrouter\n")
                # No OPENROUTER_API_KEY

            with patch.dict(os.environ, {}, clear=True):
                # Should not raise with validate=False
                settings = Settings.from_env_file(env_file, validate=False)
                assert settings.llm_provider == "openrouter"
                assert settings.openrouter_api_key is None


class TestSettingsRoundTrip:
    """Test round-trip conversion: Settings → env dict → Settings."""

    def test_roundtrip_preserves_all_values(self):
        """Test that round-trip conversion preserves all values."""
        original = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="custom-model",
            zen_api_key="zen-key",  # Can have both
            timezone="America/New_York",
            qdrant_port=6334,
            debug=True,
            browser_device="desktop",
        )

        # Convert to env dict
        env_dict = original.to_env_dict()

        # Write to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                for key, value in env_dict.items():
                    f.write(f"{key}={value}\n")

            with patch.dict(os.environ, {}, clear=True):
                # Load back
                restored = Settings.from_env_file(env_file, validate=True)

        # Should match original
        assert restored.llm_provider == original.llm_provider
        assert restored.openrouter_api_key == original.openrouter_api_key
        assert restored.openrouter_model == original.openrouter_model
        assert restored.zen_api_key == original.zen_api_key
        assert restored.timezone == original.timezone
        assert restored.qdrant_port == original.qdrant_port
        assert restored.debug == original.debug
        assert restored.browser_device == original.browser_device

    def test_roundtrip_with_minimal_settings(self):
        """Test round-trip with minimal valid settings."""
        original = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        env_dict = original.to_env_dict()

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                for key, value in env_dict.items():
                    f.write(f"{key}={value}\n")

            with patch.dict(os.environ, {}, clear=True):
                restored = Settings.from_env_file(env_file, validate=True)

        assert restored.llm_provider == original.llm_provider
        assert restored.zen_api_key == original.zen_api_key

    def test_roundtrip_preserves_types(self):
        """Test that round-trip preserves data types correctly."""
        original = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_port=6334,
            vnc_port=5901,
            debug=True,
            assistance_link_expiration=600,
        )

        env_dict = original.to_env_dict()

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                for key, value in env_dict.items():
                    f.write(f"{key}={value}\n")

            restored = Settings.from_env_file(env_file, validate=True)

        # Check types are preserved
        assert isinstance(restored.qdrant_port, int)
        assert isinstance(restored.vnc_port, int)
        assert isinstance(restored.debug, bool)
        assert isinstance(restored.assistance_link_expiration, int)
        assert isinstance(restored.zen_api_key, str)


class TestSettingsEnvFileEdgeCases:
    """Test edge cases in env file loading."""

    def test_from_env_file_ignores_comments(self):
        """Test that comments in .env file are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            with open(env_file, "w") as f:
                f.write("# This is a comment\n")
                f.write("LLM_PROVIDER=zen\n")
                f.write("# Another comment\n")
                f.write("ZEN_API_KEY=test-key\n")

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env_file(env_file, validate=True)

                assert settings.llm_provider == "zen"
                assert settings.zen_api_key == "test-key"

    def test_from_env_file_handles_empty_lines(self):
        """Test that empty lines in .env file are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            with open(env_file, "w") as f:
                f.write("\n")
                f.write("LLM_PROVIDER=zen\n")
                f.write("\n")
                f.write("\n")
                f.write("ZEN_API_KEY=test-key\n")
                f.write("\n")

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env_file(env_file, validate=True)

                assert settings.llm_provider == "zen"
                assert settings.zen_api_key == "test-key"

    def test_from_env_file_with_quotes(self):
        """Test that quoted values in .env file are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")

            with open(env_file, "w") as f:
                f.write('LLM_PROVIDER="zen"\n')
                f.write("ZEN_API_KEY='test-key'\n")

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env_file(env_file, validate=True)

                # python-dotenv strips quotes
                assert settings.llm_provider == "zen"
                assert settings.zen_api_key == "test-key"
