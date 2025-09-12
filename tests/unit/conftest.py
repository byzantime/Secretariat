"""Fixtures for unit tests that don't require database dependencies."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from src import create_app


@pytest.fixture
def app():
    """Create an application for unit testing with mocked dependencies."""
    # Create the app with test config
    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "SERVER_NAME": "localhost",
        "SECRET_KEY": "test_key",
        "SENTRY_DSN": "",  # Disable Sentry for tests
    }

    # Mock database and user manager extensions to avoid SQLAlchemy dependencies
    with patch("src.extensions.init_extensions"):
        app = create_app(test_config)

        # Mock the extensions that would normally be initialized
        app.extensions["database"] = MagicMock()
        app.extensions["user_manager"] = MagicMock()
        app.extensions["connection_manager"] = MagicMock()

    # Setup app context for testing
    ctx = app.app_context()
    ctx.push()

    yield app

    # Teardown
    ctx.pop()


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def cli_runner(app):
    """Create a CLI runner for testing CLI commands."""
    return app.test_cli_runner()
