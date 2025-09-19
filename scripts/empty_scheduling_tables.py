#!/usr/bin/env python3
"""
Script to empty scheduling-related database tables.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from sqlalchemy import text

from src.config import Config
from src.modules.database import Database

load_dotenv()


async def empty_scheduling_tables():
    """Empty all scheduling-related tables."""
    print("Emptying scheduling-related database tables...")
    print("==============================================")

    # Initialize database connection
    config = Config()

    # Create a mock config object that behaves like a dict
    class MockConfig:
        def __init__(self, config_obj):
            self._config = config_obj

        def get(self, key, default=None):
            return getattr(self._config, key, default)

    mock_config = MockConfig(config)
    # Create a mock logger
    import logging

    mock_logger = logging.getLogger("mock_app")
    # Create a mock app object with config, logger, and extensions attributes
    mock_app = type(
        "App", (), {"config": mock_config, "logger": mock_logger, "extensions": {}}
    )()
    db = Database()
    db.init_app(mock_app)

    try:
        # Check if session factory is initialized
        if not db.session_factory:
            raise RuntimeError("Database session factory not initialized")

        # Get session from factory
        session = db.session_factory()

        # Delete all records from scheduled_tasks table
        print("Deleting all records from scheduled_tasks table...")

        # Use SQLAlchemy text() for raw SQL
        await session.execute(text("DELETE FROM scheduled_tasks"))

        # Commit the transaction
        await session.commit()

        print("✓ All scheduling-related tables have been emptied successfully")

    except Exception as e:
        print(f"✗ Error emptying tables: {e}")
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(empty_scheduling_tables())
