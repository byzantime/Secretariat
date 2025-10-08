"""Fixtures for unit tests that don't require database dependencies."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from src import create_app


@pytest_asyncio.fixture
async def app():
    """Create an application for unit testing with mocked dependencies."""
    import os

    # Set required env vars before app creation (config.py validates these)
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("SECRET_KEY", "test-secret-key")

    # Create the app with test config
    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "SERVER_NAME": "localhost",
        "SECRET_KEY": "test_key",
    }

    # Mock database and user manager extensions to avoid SQLAlchemy dependencies
    with patch("src.extensions.init_extensions"):
        app = create_app(test_config)

        # Mock the extensions that would normally be initialized
        from unittest.mock import AsyncMock

        mock_db = MagicMock()

        # Create a proper async context manager for session factory
        mock_session = AsyncMock()
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = MagicMock(return_value=mock_session_context)
        mock_db.session_factory = mock_session_factory

        # Mock scheduling service
        mock_scheduling = MagicMock()
        mock_scheduling.schedule_agent_execution = AsyncMock()

        app.extensions["database"] = mock_db
        app.extensions["user_manager"] = MagicMock()
        app.extensions["connection_manager"] = MagicMock()
        app.extensions["scheduling"] = mock_scheduling

    # Setup app context for testing
    async with app.app_context():
        yield app


@pytest_asyncio.fixture
async def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest_asyncio.fixture
async def cli_runner(app):
    """Create a CLI runner for testing CLI commands."""
    return app.test_cli_runner()


@pytest.fixture
def conversation_manager():
    """Mock conversation manager."""
    return MagicMock()


@pytest.fixture
def mock_conversation_id():
    """Mock conversation ID."""
    import uuid

    return str(uuid.uuid4())
