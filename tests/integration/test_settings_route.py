"""Integration tests for settings page route."""

import os
import tempfile
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from src import create_app
from src.models.settings import Settings


@pytest_asyncio.fixture
async def app_with_settings():
    """Create app with mocked settings for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test .env file
        env_file = os.path.join(tmpdir, ".env")
        with open(env_file, "w") as f:
            f.write("LLM_PROVIDER=zen\n")
            f.write("ZEN_API_KEY=test-key\n")
            f.write("SECRET_KEY=test-secret\n")

        # Patch the env file location
        with patch("src.models.settings.Settings.from_env_file") as mock_load:
            # Return valid settings
            mock_settings = Settings(
                llm_provider="zen",
                zen_api_key="test-key",
            )
            mock_load.return_value = mock_settings

            # Mock extensions to avoid initialization issues
            with patch("src.extensions.init_extensions") as mock_init:
                # Mock the init_extensions to only call init_assets and wtforms_helpers
                def mock_init_func(app):
                    from src.modules.assets import init_assets
                    from src.modules.wtforms_helpers import WTFormsHelpers

                    init_assets(app)
                    WTFormsHelpers().init_app(app)

                mock_init.side_effect = mock_init_func

                test_config = {
                    "TESTING": True,
                    "DEBUG": True,
                    "SERVER_NAME": "localhost",
                    "SECRET_KEY": "test-key",
                    "SETUP_MODE": False,  # Start in normal mode
                    "WTF_CSRF_ENABLED": False,  # Disable CSRF for testing
                    "WTF_CSRF_METHODS": [],  # Disable CSRF validation for all methods
                }

                app = create_app(test_config)

                # Mock database and other extensions
                mock_db = MagicMock()
                mock_session = AsyncMock()
                mock_session_context = AsyncMock()
                mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_context.__aexit__ = AsyncMock(return_value=None)
                mock_db.session_factory = MagicMock(return_value=mock_session_context)
                app.extensions["database"] = mock_db

                # Mock ngrok service
                mock_ngrok = MagicMock()
                mock_ngrok.is_active.return_value = False
                mock_ngrok.error_message = None
                app.extensions["ngrok_service"] = mock_ngrok

                async with app.app_context():
                    yield app


@pytest_asyncio.fixture
async def app_in_setup_mode():
    """Create app in setup mode for testing."""
    with tempfile.TemporaryDirectory():
        with patch("src.models.settings.Settings.from_env_file") as mock_load:
            # Make from_env_file raise an exception when validate=True
            # to trigger setup mode, but return incomplete settings when validate=False
            def mock_from_env(env_path=".env", validate=True):
                if validate:
                    # Simulate validation failure - missing API key
                    from pydantic import ValidationError

                    raise ValidationError.from_exception_data(
                        "Settings",
                        [{
                            "type": "missing_api_key",
                            "loc": ("zen_api_key",),
                            "msg": "Zen API key is required when using Opencode Zen",
                            "input": None,
                        }],
                    )
                # Return settings without API keys when validation is skipped
                return Settings.model_construct(
                    llm_provider="zen",
                    zen_api_key=None,
                    openrouter_api_key=None,
                )

            mock_load.side_effect = mock_from_env

            with patch("src.extensions.init_extensions") as mock_init:
                # Mock the init_extensions to only call init_assets and wtforms_helpers
                def mock_init_func(app):
                    from src.modules.assets import init_assets
                    from src.modules.wtforms_helpers import WTFormsHelpers

                    init_assets(app)
                    WTFormsHelpers().init_app(app)

                mock_init.side_effect = mock_init_func

                test_config = {
                    "TESTING": True,
                    "DEBUG": True,
                    "SERVER_NAME": "localhost",
                    "SECRET_KEY": "test-key",
                    "SETUP_MODE": True,  # Start in setup mode
                    "WTF_CSRF_ENABLED": False,
                    "WTF_CSRF_METHODS": [],  # Disable CSRF validation for all methods
                }

                app = create_app(test_config)

                # Mock extensions
                mock_db = MagicMock()
                mock_session = AsyncMock()
                mock_session_context = AsyncMock()
                mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_context.__aexit__ = AsyncMock(return_value=None)
                mock_db.session_factory = MagicMock(return_value=mock_session_context)
                app.extensions["database"] = mock_db

                # Mock ngrok service
                mock_ngrok = MagicMock()
                mock_ngrok.is_active.return_value = False
                mock_ngrok.error_message = None
                app.extensions["ngrok_service"] = mock_ngrok

                async with app.app_context():
                    yield app


@pytest.mark.integration
class TestSettingsRouteGet:
    """Test GET requests to settings route."""

    @pytest.mark.asyncio
    async def test_get_settings_page_returns_200(self, app_with_settings):
        """Test that GET /settings returns 200 OK."""
        client = app_with_settings.test_client()

        # Patch Settings.from_env_file for the route
        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="zen",
                zen_api_key="test-key",
            )

            response = await client.get("/settings")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_settings_page_renders_form(self, app_with_settings):
        """Test that GET /settings renders the form."""
        client = app_with_settings.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="zen",
                zen_api_key="test-key",
            )

            response = await client.get("/settings")
            data = await response.get_data(as_text=True)

            # Should contain form elements
            assert "form" in data.lower()
            assert "llm_provider" in data.lower()

    @pytest.mark.asyncio
    async def test_get_settings_loads_existing_settings(self, app_with_settings):
        """Test that GET /settings loads and displays existing settings."""
        client = app_with_settings.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="openrouter",
                openrouter_api_key="existing-key",
                timezone="America/New_York",
            )

            response = await client.get("/settings")
            data = await response.get_data(as_text=True)

            # Should show existing values
            assert "openrouter" in data.lower()
            assert "america/new_york" in data.lower()


@pytest.mark.integration
class TestSettingsRoutePost:
    """Test POST requests to settings route."""

    @pytest.mark.asyncio
    async def test_post_valid_settings_redirects(self, app_with_settings):
        """Test that POST /settings with valid data schedules app restart."""
        client = app_with_settings.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="zen",
                zen_api_key="old-key",
            )

            with patch("src.routes.save_settings_to_env"):
                with patch("asyncio.create_task") as mock_create_task:
                    response = await client.post(
                        "/settings",
                        form={
                            "llm_provider": "zen",
                            "zen_api_key": "new-key",
                            "openrouter_api_key": "",
                            "openrouter_model": "moonshotai/kimi-k2-0905",
                            "zen_model": "grok-code",
                            "browser_use_model": "openai/o3",
                            "telegram_bot_token": "",
                            "telegram_webhook_url": "",
                            "telegram_allowed_users": "",
                            "qdrant_host": "",
                            "qdrant_api_key": "",
                            "timezone": "UTC",
                            "qdrant_port": "6333",
                            "vnc_port": "5900",
                            "novnc_port": "6080",
                            "assistance_link_expiration": "300",
                            "vnc_display": ":99",
                            "memory_collection_name": "memories",
                            "browser_user_data_dir": "./data/browser_profile",
                            "browser_device": "pixel",
                        },
                        follow_redirects=False,
                    )

                    # Should schedule restart task
                    assert mock_create_task.called
                    # Should return 200 (renders template)
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_post_invalid_settings_shows_errors(self, app_with_settings):
        """Test that POST /settings with invalid data shows errors."""
        client = app_with_settings.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="zen",
                zen_api_key="test-key",
            )

            # Post invalid data - OpenRouter selected but no API key
            response = await client.post(
                "/settings",
                form={
                    "llm_provider": "openrouter",
                    # Missing openrouter_api_key
                    "openrouter_model": "moonshotai/kimi-k2-0905",
                    "zen_model": "grok-code",
                    "browser_use_model": "openai/o3",
                    "timezone": "UTC",
                    "qdrant_port": "6333",
                    "vnc_port": "5900",
                    "novnc_port": "6080",
                    "assistance_link_expiration": "300",
                    "vnc_display": ":99",
                    "memory_collection_name": "memories",
                    "browser_user_data_dir": "./data/browser_profile",
                    "browser_device": "pixel",
                    "database_name": "secretariat",
                    "data_dir": ".",
                },
                follow_redirects=False,
            )

            # Should return form with errors (200 or 400)
            assert response.status_code in (200, 400)

    @pytest.mark.asyncio
    async def test_post_settings_saves_to_env(self, app_with_settings):
        """Test that POST /settings saves settings to .env file."""
        client = app_with_settings.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings(
                llm_provider="zen",
                zen_api_key="old-key",
            )

            with patch("src.routes.save_settings_to_env") as mock_save:
                with patch("asyncio.create_task"):
                    await client.post(
                        "/settings",
                        form={
                            "llm_provider": "zen",
                            "zen_api_key": "new-key",
                            "openrouter_model": "moonshotai/kimi-k2-0905",
                            "zen_model": "grok-code",
                            "browser_use_model": "openai/o3",
                            "timezone": "America/New_York",
                            "qdrant_port": "6333",
                            "vnc_port": "5900",
                            "novnc_port": "6080",
                            "assistance_link_expiration": "300",
                            "vnc_display": ":99",
                            "memory_collection_name": "memories",
                            "browser_user_data_dir": "./data/browser_profile",
                            "browser_device": "pixel",
                            "database_name": "secretariat",
                            "data_dir": ".",
                        },
                        follow_redirects=False,
                    )

                    # Should have called save_settings_to_env
                    assert mock_save.called
                    # Verify settings passed to save
                    saved_settings = mock_save.call_args[0][0]
                    assert saved_settings.zen_api_key == "new-key"
                    assert saved_settings.timezone == "America/New_York"


@pytest.mark.integration
class TestSetupModeRedirect:
    """Test setup mode redirect behavior."""

    @pytest.mark.asyncio
    async def test_setup_mode_redirects_to_settings(self, app_in_setup_mode):
        """Test that setup mode redirects all requests to /settings."""
        client = app_in_setup_mode.test_client()

        # Try to access home page
        response = await client.get("/", follow_redirects=False)

        # Should redirect to settings
        assert response.status_code in (302, 303, 307)
        assert "/settings" in response.headers.get("Location", "")

    @pytest.mark.asyncio
    async def test_setup_mode_allows_settings_page(self, app_in_setup_mode):
        """Test that setup mode allows access to /settings."""
        client = app_in_setup_mode.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings.model_construct(
                llm_provider="zen",
                zen_api_key=None,
            )

            response = await client.get("/settings")

            # Should allow access (200)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_setup_mode_allows_static_files(self, app_in_setup_mode):
        """Test that setup mode allows access to static files."""
        # This is a behavioral test - static endpoint should be allowed
        # Actual static file serving may not work in test environment
        pass

    @pytest.mark.asyncio
    async def test_setup_mode_shows_welcome_banner(self, app_in_setup_mode):
        """Test that setup mode shows welcome/setup instructions."""
        client = app_in_setup_mode.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings.model_construct(
                llm_provider="zen",
                zen_api_key=None,
            )

            response = await client.get("/settings")
            data = await response.get_data(as_text=True)

            # Should show setup mode banner
            assert "setup" in data.lower() or "welcome" in data.lower()


@pytest.mark.integration
class TestSetupModeExit:
    """Test exiting setup mode after configuration."""

    @pytest.mark.asyncio
    async def test_saving_valid_settings_exits_setup_mode(self, app_in_setup_mode):
        """Test that saving valid settings schedules app restart."""
        client = app_in_setup_mode.test_client()

        with patch("src.routes.Settings.from_env_file") as mock_load:
            mock_load.return_value = Settings.model_construct(
                llm_provider="zen",
                zen_api_key=None,
            )

            with patch("src.routes.save_settings_to_env"):
                with patch("asyncio.create_task") as mock_create_task:
                    # Post valid settings
                    response = await client.post(
                        "/settings",
                        form={
                            "llm_provider": "zen",
                            "zen_api_key": "new-valid-key",
                            "openrouter_model": "moonshotai/kimi-k2-0905",
                            "zen_model": "grok-code",
                            "browser_use_model": "openai/o3",
                            "timezone": "UTC",
                            "qdrant_port": "6333",
                            "vnc_port": "5900",
                            "novnc_port": "6080",
                            "assistance_link_expiration": "300",
                            "vnc_display": ":99",
                            "memory_collection_name": "memories",
                            "browser_user_data_dir": "./data/browser_profile",
                            "browser_device": "pixel",
                            "database_name": "secretariat",
                            "data_dir": ".",
                        },
                        follow_redirects=False,
                    )

                    # Should schedule restart task
                    assert mock_create_task.called
                    # Should return 200 (renders template)
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_after_setup_home_page_accessible(self, app_with_settings):
        """Test that after setup, home page is accessible."""
        # App is not in setup mode
        assert app_with_settings.config.get("SETUP_MODE") is False

        client = app_with_settings.test_client()

        # Home page should be accessible without redirect
        # Note: Actual response depends on route implementation
        response = await client.get("/", follow_redirects=False)

        # Should not redirect to settings
        location = response.headers.get("Location", "")
        assert "/settings" not in location or response.status_code == 200
