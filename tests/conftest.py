import pytest

from src import create_app


@pytest.fixture
def app():
    """Create an application for testing."""
    # Create the app with test config
    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "SERVER_NAME": "localhost",
        "SECRET_KEY": "test_key",
    }
    app = create_app(test_config)

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
