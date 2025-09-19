"""Test interactive scheduling functionality."""

import uuid
from datetime import datetime
from datetime import timedelta

import pytest

from src.models.schedule_config import CronSchedule
from src.models.schedule_config import OnceSchedule
from src.models.scheduled_task import ScheduledTask
from src.tools.scheduling_tools import setup_automation


@pytest.mark.asyncio
async def test_interactive_scheduling(app, conversation_manager, mock_conversation_id):
    """Test that interactive tasks use streaming mode."""
    # Create a mock context like the agent would
    ctx = type("MockContext", (), {"deps": {"conversation_id": mock_conversation_id}})()

    # Test interactive task
    result = await setup_automation(
        ctx=ctx,
        agent_instructions="Send me a motivational quote",
        schedule_config=OnceSchedule(
            type="once",
            when=(datetime.now() + timedelta(minutes=1)).isoformat(),
        ),
        interactive=True,
    )

    # Verify task was created with interactive=True
    assert result["status"] == "success"
    assert "task_id" in result

    # Verify the task was stored with interactive=True
    async with app.extensions["database"].session_factory() as session:
        task = await ScheduledTask.get_by_id(session, uuid.UUID(result["task_id"]))
        assert task is not None
        assert task.interactive is True
        assert task.agent_instructions == "Send me a motivational quote"


@pytest.mark.asyncio
async def test_non_interactive_scheduling(
    app, conversation_manager, mock_conversation_id
):
    """Test that non-interactive tasks use batch mode (default)."""
    # Create a mock context like the agent would
    ctx = type("MockContext", (), {"deps": {"conversation_id": mock_conversation_id}})()

    # Test non-interactive task (default)
    result = await setup_automation(
        ctx=ctx,
        agent_instructions="Backup database",
        schedule_config=CronSchedule(
            type="cron",
            when="0 2 * * *",  # Daily at 2 AM
        ),
    )

    # Verify task was created with interactive=False (default)
    assert result["status"] == "success"
    assert "task_id" in result

    # Verify the task was stored with interactive=False
    async with app.extensions["database"].session_factory() as session:
        task = await ScheduledTask.get_by_id(session, uuid.UUID(result["task_id"]))
        assert task is not None
        assert task.interactive is False
        assert task.agent_instructions == "Backup database"


@pytest.mark.asyncio
async def test_scheduling_service_parameters(
    app, conversation_manager, mock_conversation_id
):
    """Test that scheduling service correctly passes interactive parameter."""
    scheduling_service = app.extensions["scheduling"]

    task_id = uuid.uuid4()
    conversation_id = mock_conversation_id

    # Test with interactive=True
    job_id = await scheduling_service.schedule_agent_execution(
        task_id=task_id,
        conversation_id=conversation_id,
        agent_instructions="Test interactive task",
        schedule_config={
            "type": "once",
            "when": datetime.now().isoformat(),
        },  # Keep as dict for service compatibility
        interactive=True,
    )

    assert job_id == f"agent_task_{task_id}"

    # Verify task was stored with interactive=True
    async with app.extensions["database"].session_factory() as session:
        task = await ScheduledTask.get_by_id(session, task_id)
        assert task is not None
        assert task.interactive is True
