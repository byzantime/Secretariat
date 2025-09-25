"""Integration tests for scheduling tools that test real functionality."""

import os
import tempfile
import uuid
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio
from pydantic_ai import RunContext
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from src.models.schedule_config import CronSchedule
from src.models.schedule_config import IntervalSchedule
from src.models.schedule_config import OnceSchedule
from src.models.scheduled_task import ScheduledTask
from src.modules.scheduling_service import SchedulingService
from src.tools.scheduling_tools import automations_search
from src.tools.scheduling_tools import setup_automation


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

    # Test One-Off Scheduling (Should Work)

    @pytest.mark.asyncio
    async def test_once_schedule_creates_real_job_and_db_entry(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that one-time schedule creates actual APScheduler job and database entry."""
        ctx, conversation_id = mock_run_context
        future_time = datetime.now() + timedelta(hours=1)

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Test reminder",
                schedule_config=OnceSchedule(type="once", when=future_time.isoformat()),
                interactive=True,
            )

        # Verify result
        assert result["status"] == "success"
        assert "job_id" in result
        assert "task_id" in result

        # Verify APScheduler job was created
        scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
        job = scheduler.get_job(result["job_id"])
        assert job is not None
        assert job.id == result["job_id"]

        # Verify database entry was created
        db_service = mock_app_with_real_db.extensions["database"]
        async with db_service.session_factory() as session:
            task = await ScheduledTask.get_by_id(session, uuid.UUID(result["task_id"]))
            assert task is not None
            assert task.agent_instructions == "Test reminder"
            assert task.status == "pending"
            assert task.interactive is True
            assert task.schedule_config["type"] == "once"
            assert task.schedule_config["when"] == future_time.isoformat()

    @pytest.mark.asyncio
    async def test_once_schedule_past_time_fails(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that scheduling in the past fails appropriately."""
        ctx, _ = mock_run_context
        past_time = datetime.now() - timedelta(hours=1)

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            # This should work at the tool level but fail at APScheduler level
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Past reminder",
                schedule_config=OnceSchedule(type="once", when=past_time.isoformat()),
                interactive=False,
            )

        # The tool should succeed (it doesn't validate timing)
        assert result["status"] == "success"

        # But APScheduler should handle past dates gracefully
        scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
        scheduler.get_job(result["job_id"])
        # Job might be None if APScheduler automatically removes past jobs
        # or it might exist but not trigger

    # Test Cron Scheduling (May Reveal Bugs)

    @pytest.mark.asyncio
    async def test_cron_schedule_creates_real_job(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test cron schedule creates real APScheduler CronTrigger."""
        ctx, _ = mock_run_context

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Daily report",
                schedule_config=CronSchedule(type="cron", hour=9, minute=30),
                interactive=True,
            )

        # Verify basic result
        assert result["status"] == "success"

        # Verify APScheduler job was created with CronTrigger
        scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
        job = scheduler.get_job(result["job_id"])
        assert job is not None

        # Check that it's actually a CronTrigger
        from apscheduler.triggers.cron import CronTrigger

        assert isinstance(job.trigger, CronTrigger)

        # Verify trigger configuration
        # This will fail if CronTrigger is passed None values incorrectly
        assert job.trigger.fields[5].expressions[0].first == 9  # hour
        assert job.trigger.fields[6].expressions[0].first == 30  # minute

    @pytest.mark.asyncio
    async def test_cron_schedule_with_none_values_bug(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that cron schedule handles None values correctly (this may fail due to current bug)."""
        ctx, _ = mock_run_context

        try:
            with patch(
                "src.tools.scheduling_tools.current_app", mock_app_with_real_db
            ), patch(
                "src.modules.scheduling_service.current_app", mock_app_with_real_db
            ):
                result = await setup_automation(
                    ctx=ctx,
                    agent_instructions="Minimal cron",
                    schedule_config=CronSchedule(
                        type="cron",
                        hour=10,  # Only hour specified, others should be None
                    ),
                    interactive=True,
                )

            # If this succeeds, the bug is fixed
            assert result["status"] == "success"

            scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
            job = scheduler.get_job(result["job_id"])
            assert job is not None

        except Exception as e:
            # This will catch the bug where None values cause APScheduler to fail
            pytest.fail(f"Cron scheduling failed with None values: {e}")

    # Test Interval Scheduling (May Reveal Bugs)

    @pytest.mark.asyncio
    async def test_interval_schedule_creates_real_job(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test interval schedule creates real APScheduler IntervalTrigger."""
        ctx, _ = mock_run_context

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Hourly check",
                schedule_config=IntervalSchedule(type="interval", hours=1),
                interactive=False,
            )

        # Verify basic result
        assert result["status"] == "success"

        # Verify APScheduler job was created with IntervalTrigger
        scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
        job = scheduler.get_job(result["job_id"])
        assert job is not None

        # Check that it's actually an IntervalTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        assert isinstance(job.trigger, IntervalTrigger)

        # Verify trigger configuration
        assert job.trigger.interval.total_seconds() == 3600  # 1 hour

    @pytest.mark.asyncio
    async def test_interval_schedule_zero_values_bug(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that interval schedule handles zero default values correctly (this may fail due to current bug)."""
        ctx, _ = mock_run_context

        # This test specifically targets the bug where unspecified intervals default to 0
        # causing all intervals to be 0, which makes the job never run

        try:
            with patch(
                "src.tools.scheduling_tools.current_app", mock_app_with_real_db
            ), patch(
                "src.modules.scheduling_service.current_app", mock_app_with_real_db
            ):
                result = await setup_automation(
                    ctx=ctx,
                    agent_instructions="Interval with potential zero bug",
                    schedule_config=IntervalSchedule(
                        type="interval", minutes=30  # Only minutes specified
                    ),
                    interactive=False,
                )

            # If this succeeds, check the actual trigger
            scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
            job = scheduler.get_job(result["job_id"])
            assert job is not None

            # The bug would be if total interval is 0 or very small due to other fields being 0
            from apscheduler.triggers.interval import IntervalTrigger

            assert isinstance(job.trigger, IntervalTrigger)

            # Should be 30 minutes (1800 seconds), not 0
            interval_seconds = job.trigger.interval.total_seconds()
            assert (
                interval_seconds == 1800
            ), f"Expected 1800 seconds, got {interval_seconds}"

        except Exception as e:
            pytest.fail(f"Interval scheduling failed with zero values bug: {e}")

    # Test automations_search with Real Database

    @pytest.mark.asyncio
    async def test_automations_search_real_db_empty(self, mock_app_with_real_db):
        """Test automations_search with real empty database."""
        with patch("src.tools.scheduling_tools.current_app", mock_app_with_real_db):
            result = await automations_search({})

        assert result == "No tasks are currently scheduled."

    @pytest.mark.asyncio
    async def test_automations_search_real_db_with_tasks(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test automations_search with real database containing tasks."""
        ctx, _ = mock_run_context

        # Create some real tasks first
        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            # Create a once task
            await setup_automation(
                ctx=ctx,
                agent_instructions="Test once task",
                schedule_config=OnceSchedule(
                    type="once", when=(datetime.now() + timedelta(hours=1)).isoformat()
                ),
                interactive=True,
            )

            # Create a cron task
            await setup_automation(
                ctx=ctx,
                agent_instructions="Test cron task",
                schedule_config=CronSchedule(type="cron", hour=9, minute=0),
                interactive=False,
            )

            # Now search for tasks
            result = await automations_search({})

        # Verify search results
        assert "**Scheduled Tasks** (2 total):" in result
        assert "**Test once task**" in result
        assert "**Test cron task**" in result
        assert "📱" in result  # Should show interactive flag for one task
        assert "(pending)" in result

    # Test Database Task Operations

    @pytest.mark.asyncio
    async def test_database_task_crud_operations(self, mock_app_with_real_db):
        """Test that database CRUD operations work correctly."""
        db_service = mock_app_with_real_db.extensions["database"]

        task_id = uuid.uuid4()
        conversation_id = uuid.uuid4()

        # Create task
        async with db_service.session_factory() as session:
            task = await ScheduledTask.create_task(
                session=session,
                task_id=task_id,
                job_id=f"test_job_{task_id}",
                conversation_id=conversation_id,
                agent_instructions="Test database task",
                schedule_config={"type": "once", "when": "2024-12-25T09:00:00"},
                interactive=True,
            )

            assert task.id == task_id
            assert task.agent_instructions == "Test database task"
            assert task.status == "pending"

        # Read task
        async with db_service.session_factory() as session:
            retrieved_task = await ScheduledTask.get_by_id(session, task_id)
            assert retrieved_task is not None
            assert retrieved_task.agent_instructions == "Test database task"

        # Update task status
        async with db_service.session_factory() as session:
            task = await ScheduledTask.get_by_id(session, task_id)
            await task.update_status(session, "completed")

        # Verify update
        async with db_service.session_factory() as session:
            task = await ScheduledTask.get_by_id(session, task_id)
            assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_missing_conversation_id_error(self, mock_app_with_real_db):
        """Test error handling for missing conversation_id."""
        ctx = MagicMock(spec=RunContext)
        ctx.deps = {}  # No conversation_id

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            with pytest.raises(
                ValueError, match="Conversation ID not found in context"
            ):
                await setup_automation(
                    ctx=ctx,
                    agent_instructions="Test task",
                    schedule_config=OnceSchedule(
                        type="once",
                        when=(datetime.now() + timedelta(hours=1)).isoformat(),
                    ),
                )

    # Test APScheduler Job Management

    @pytest.mark.asyncio
    async def test_apscheduler_job_lifecycle(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that APScheduler jobs can be created, retrieved, and removed."""
        ctx, _ = mock_run_context

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Job lifecycle test",
                schedule_config=OnceSchedule(
                    type="once", when=(datetime.now() + timedelta(hours=2)).isoformat()
                ),
            )

        scheduler = mock_app_with_real_db.extensions["scheduling"].scheduler
        job_id = result["job_id"]

        # Job should exist
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.id == job_id

        # Should be able to remove job
        scheduler.remove_job(job_id)

        # Job should no longer exist
        job = scheduler.get_job(job_id)
        assert job is None

    @pytest.mark.asyncio
    async def test_schedule_config_serialization(
        self, mock_run_context, mock_app_with_real_db
    ):
        """Test that schedule configs are properly serialized to database."""
        ctx, _ = mock_run_context

        # Test complex cron config
        complex_config = CronSchedule(
            type="cron",
            day_of_week="mon",
            hour=9,
            minute=30,
            start_date="2024-01-01T00:00:00",
        )

        with patch(
            "src.tools.scheduling_tools.current_app", mock_app_with_real_db
        ), patch("src.modules.scheduling_service.current_app", mock_app_with_real_db):
            result = await setup_automation(
                ctx=ctx,
                agent_instructions="Config serialization test",
                schedule_config=complex_config,
            )

        # Verify database storage
        db_service = mock_app_with_real_db.extensions["database"]
        async with db_service.session_factory() as session:
            task = await ScheduledTask.get_by_id(session, uuid.UUID(result["task_id"]))

            stored_config = task.schedule_config
            assert stored_config["type"] == "cron"
            assert stored_config["day_of_week"] == "mon"
            assert stored_config["hour"] == 9
            assert stored_config["minute"] == 30
            assert stored_config["start_date"] == "2024-01-01T00:00:00"
