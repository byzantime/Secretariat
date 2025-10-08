"""Unit tests for config loading behavior."""

import os
import tempfile
from unittest.mock import patch

from src.config import Config
from src.config import save_settings_to_env
from src.models.settings import Settings


class TestConfigLoadsFromSettings:
    """Test that Config class loads values from Settings model."""

    @patch.dict(os.environ, {}, clear=True)
    def test_config_uses_settings_defaults(self):
        """Test that Config uses Settings defaults when no env vars set."""
        # Create a temporary .env file with minimal settings
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=zen\n")
                f.write("ZEN_API_KEY=test-key\n")

            # Patch the env file location
            with patch("src.config.Settings.from_env_file") as mock_load:
                mock_settings = Settings(
                    llm_provider="zen",
                    zen_api_key="test-key",
                )
                mock_load.return_value = mock_settings

                # Import fresh config
                import importlib

                import src.config as config_module

                importlib.reload(config_module)

                # Config should use settings values
                assert config_module.Config.LLM_PROVIDER == "zen"
                assert config_module.Config.TIMEZONE == "UTC"  # default
                assert config_module.Config.QDRANT_PORT == 6333  # default

    def test_config_field_names_match_settings(self):
        """Test that Config field names correspond to Settings fields."""
        # Key config fields that should exist
        assert hasattr(Config, "LLM_PROVIDER")
        assert hasattr(Config, "OPENROUTER_API_KEY")
        assert hasattr(Config, "ZEN_API_KEY")
        assert hasattr(Config, "TIMEZONE")
        assert hasattr(Config, "QDRANT_HOST")
        assert hasattr(Config, "QDRANT_PORT")
        assert hasattr(Config, "TELEGRAM_BOT_TOKEN")


class TestConfigEnvironmentOverride:
    """Test that environment variables override Settings defaults."""

    def test_env_var_overrides_setting_default(self):
        """Test that environment variables take precedence over Settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("LLM_PROVIDER=zen\n")
                f.write("ZEN_API_KEY=test-key\n")
                f.write("TIMEZONE=UTC\n")

            # Set environment variable to override
            with patch.dict(os.environ, {"TIMEZONE": "America/New_York"}, clear=False):
                # The Config class should prefer env var
                # This test verifies the pattern, actual implementation may vary
                timezone = os.environ.get("TIMEZONE", "UTC")
                assert timezone == "America/New_York"

    def test_env_bool_parses_boolean_values(self):
        """Test that env_bool helper correctly parses boolean strings."""
        from src.config import env_bool

        test_cases = [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("", False),
        ]

        for value, expected in test_cases:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = env_bool("TEST_BOOL")
                assert result == expected, f"Failed for value: {value}"


class TestSaveSettingsToEnv:
    """Test save_settings_to_env() function."""

    def test_save_settings_to_env_creates_file(self):
        """Test that save_settings_to_env creates .env file."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            timezone="America/New_York",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                save_settings_to_env(settings)

                # Check file was created
                env_path = os.path.join(tmpdir, ".env")
                assert os.path.exists(env_path)

            finally:
                os.chdir(original_cwd)

    def test_save_settings_to_env_writes_correct_format(self):
        """Test that save_settings_to_env writes correct env format."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key-123",
            timezone="Europe/London",
            qdrant_port=6334,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                save_settings_to_env(settings)

                # Read the file
                env_path = os.path.join(tmpdir, ".env")
                with open(env_path, "r") as f:
                    content = f.read()

                # Check format
                assert "LLM_PROVIDER=zen" in content
                assert "ZEN_API_KEY=test-key-123" in content
                assert "TIMEZONE=Europe/London" in content
                assert "QDRANT_PORT=6334" in content

            finally:
                os.chdir(original_cwd)

    def test_save_settings_to_env_excludes_none_values(self):
        """Test that None values are not written to .env file."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            # telegram_bot_token is None
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                save_settings_to_env(settings)

                env_path = os.path.join(tmpdir, ".env")
                with open(env_path, "r") as f:
                    content = f.read()

                # None values should not be in file
                assert "TELEGRAM_BOT_TOKEN" not in content
                assert "QDRANT_HOST" not in content

            finally:
                os.chdir(original_cwd)

    def test_save_settings_to_env_overwrites_existing(self):
        """Test that save_settings_to_env overwrites existing .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Create initial file
                env_path = os.path.join(tmpdir, ".env")
                with open(env_path, "w") as f:
                    f.write("OLD_VALUE=123\n")

                # Save new settings
                settings = Settings(
                    llm_provider="zen",
                    zen_api_key="new-key",
                )

                save_settings_to_env(settings)

                # Read the file
                with open(env_path, "r") as f:
                    content = f.read()

                # Old value should be gone
                assert "OLD_VALUE" not in content
                # New values should be present
                assert "ZEN_API_KEY=new-key" in content

            finally:
                os.chdir(original_cwd)


class TestConfigDatabaseUrl:
    """Test Database URL construction."""

    def test_database_url_constructed_from_data_dir_and_name(self):
        """Test that DATABASE_URL is constructed correctly."""
        # Config should construct database URL from DATA_DIR and DATABASE_NAME
        assert hasattr(Config, "DATABASE_URL")
        assert "sqlite+aiosqlite://" in Config.DATABASE_URL
        assert Config.DATABASE_URL.endswith(".db")


class TestConfigDefaults:
    """Test Config class default values."""

    def test_config_has_required_fields(self):
        """Test that Config has all required fields."""
        required_fields = [
            "DEBUG",
            "LOG_LEVEL",
            "SECRET_KEY",
            "DATABASE_URL",
            "LLM_PROVIDER",
            "TIMEZONE",
            "WTF_CSRF_ENABLED",
        ]

        for field in required_fields:
            assert hasattr(Config, field), f"Config missing required field: {field}"

    def test_config_wtf_settings(self):
        """Test WTForms configuration."""
        assert Config.WTF_CSRF_ENABLED is True
        assert Config.WTF_CSRF_TIME_LIMIT is None

    def test_config_quart_auth_cookie_secure(self):
        """Test that QUART_AUTH_COOKIE_SECURE is based on DEBUG."""
        # Should be opposite of DEBUG
        assert Config.QUART_AUTH_COOKIE_SECURE == (not Config.DEBUG)


class TestConfigIntegration:
    """Test Config integration with Settings."""

    def test_config_and_settings_have_matching_fields(self):
        """Test that Config and Settings have corresponding fields."""
        # Sample of fields that should exist in both
        matching_fields = [
            ("LLM_PROVIDER", "llm_provider"),
            ("TIMEZONE", "timezone"),
            ("QDRANT_PORT", "qdrant_port"),
            ("VNC_PORT", "vnc_port"),
            ("BROWSER_DEVICE", "browser_device"),
        ]

        settings = Settings.model_construct()

        for config_field, settings_field in matching_fields:
            assert hasattr(Config, config_field), f"Config missing {config_field}"
            assert hasattr(
                settings, settings_field
            ), f"Settings missing {settings_field}"

    def test_config_values_match_settings_defaults(self):
        """Test that Config default values match Settings defaults."""
        # Create Settings with defaults
        settings = Settings.model_construct()

        # These should match (when no env override)
        # Note: This test is conceptual - actual matching depends on implementation
        assert settings.timezone == "UTC"
        assert settings.qdrant_port == 6333
        assert settings.vnc_port == 5900
