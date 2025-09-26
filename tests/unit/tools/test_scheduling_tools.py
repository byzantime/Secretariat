"""Integration tests for scheduling tools that test real functionality."""

import os
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic_ai import RunContext
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from src.modules.scheduling_service import SchedulingService


class TestSchedulingToolsIntegration:
    """Integration tests for scheduling tools with real database and APScheduler."""

    @pytest_asyncio.fixture
    async def test_db_engine(self):
        """Create a temporary SQLite database for testing."""
        # Create temporary database file
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        try:
            # Create async engine for SQLite
            database_url = f"sqlite+aiosqlite:///{db_path}"
            sync_database_url = f"sqlite:///{db_path}"

            async_engine = create_async_engine(database_url)
            sync_engine = create_engine(sync_database_url)

            # Create tables with SQLite-compatible schema
            # Need to override JSONB and UUID for SQLite compatibility
            import sqlalchemy as sa

            # Create a test-compatible table schema
            async with async_engine.begin() as conn:
                # Create APScheduler jobs table manually for SQLite
                await conn.execute(sa.text("""
                    CREATE TABLE IF NOT EXISTS apscheduler_jobs (
                        id VARCHAR(191) NOT NULL,
                        next_run_time REAL,
                        job_state BLOB NOT NULL,
                        PRIMARY KEY (id)
                    )
                """))

                # Create scheduled_tasks table with SQLite-compatible types
                await conn.execute(sa.text("""
                    CREATE TABLE IF NOT EXISTS scheduled_tasks (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        job_id VARCHAR(255) NOT NULL UNIQUE,
                        conversation_id VARCHAR(36) NOT NULL,
                        agent_instructions TEXT NOT NULL,
                        schedule_config TEXT NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'pending',
                        failure_count INTEGER NOT NULL DEFAULT 0,
                        error_message TEXT,
                        interactive BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_run TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                await conn.commit()

            yield async_engine, sync_engine
        finally:
            # Cleanup
            try:
                await async_engine.dispose()
                sync_engine.dispose()
                os.unlink(db_path)
            except Exception:
                pass

    @pytest_asyncio.fixture
    async def mock_app_with_real_db(self, test_db_engine):
        """Create a mock app with real database and scheduling service."""
        async_engine, sync_engine = test_db_engine

        mock_app = MagicMock()
        mock_app.config = {"TIMEZONE": "UTC"}
        mock_app.logger = MagicMock()

        # Create real database service
        from src.modules.database import Database

        db_service = Database()
        db_service.async_engine = async_engine
        db_service.sync_engine = sync_engine

        # Create session factory
        from sqlalchemy.ext.asyncio import async_sessionmaker

        db_service.session_factory = async_sessionmaker(
            bind=async_engine, class_=AsyncSession, expire_on_commit=False
        )

        # Create real scheduling service
        scheduling_service = SchedulingService()
        scheduling_service.db = db_service

        # Initialize scheduler with SQLAlchemy jobstore for testing (same as production)
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        jobstores = {
            "default": SQLAlchemyJobStore(
                engine=sync_engine,  # Use SQLite sync engine
                tablename="apscheduler_jobs",
            )
        }
        scheduling_service.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 30,
            },
            timezone="UTC",
        )

        # Start scheduler
        scheduling_service.scheduler.start()

        # Set up extensions
        mock_app.extensions = {
            "database": db_service,
            "scheduling": scheduling_service,
        }

        yield mock_app

        # Cleanup
        try:
            scheduling_service.scheduler.shutdown(wait=True)
        except Exception:
            pass

    @pytest.fixture
    def mock_run_context(self):
        """Mock RunContext with conversation_id."""
        conversation_id = uuid.uuid4()
        ctx = MagicMock(spec=RunContext)
        ctx.deps = {"conversation_id": conversation_id}
        return ctx, conversation_id
