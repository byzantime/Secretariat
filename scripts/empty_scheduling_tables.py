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
from sqlalchemy import delete

from src.config import Config
from src.models.scheduled_task import ScheduledTask
from src.modules.database import Database

load_dotenv()


async def empty_scheduling_tables():
    """Empty all scheduling-related tables."""
    print("Emptying scheduling-related database tables...")
    print("==============================================")

    # Initialize database connection
    config = Config()

    # Create a simple mock app object with required attributes
    import logging

    mock_logger = logging.getLogger("script")

    # Create config dict that behaves like app.config
    class AppConfig(dict):
        def __init__(self, config_obj):
            super().__init__()
            # Copy all class attributes from config class
            for key in dir(config_obj):
                if not key.startswith("_") and not callable(getattr(config_obj, key)):
                    value = getattr(config_obj, key)
                    self[key] = value

        def get(self, key, default=None):
            return super().get(key, default)

    mock_config = AppConfig(config)
    mock_app = type(
        "App", (), {"config": mock_config, "logger": mock_logger, "extensions": {}}
    )()

    db = Database()
    db.init_app(mock_app)

    try:
        # Use proper async session via async generator
        async for session in db.get_session():
            # Delete all records from scheduled_tasks table using ORM
            print("Deleting all records from scheduled_tasks table...")

            # Count existing records first
            from sqlalchemy import func

            count_result = await session.execute(func.count(ScheduledTask.id))
            record_count = count_result.scalar()
            print(f"Found {record_count} records to delete")

            if record_count > 0:
                # Use ORM delete statement
                delete_stmt = delete(ScheduledTask)
                result = await session.execute(delete_stmt)
                await session.commit()
                print(f"✓ Deleted {result.rowcount} records from scheduled_tasks table")
            else:
                print("✓ No records found in scheduled_tasks table")

        print("✓ All scheduling-related tables have been emptied successfully")

    except Exception as e:
        print(f"✗ Error emptying tables: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # Close the engine properly
        if db.engine:
            await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(empty_scheduling_tables())
