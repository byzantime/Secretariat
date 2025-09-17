"""Scheduling tools for agent execution."""

import uuid
from typing import Any
from typing import Dict

from pydantic_ai import RunContext


async def setup_automation(
    ctx: RunContext[Dict[str, Any]],
    agent_instructions: str,
    schedule_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Use this tool to schedule the AI agent to perform tasks automatically at specific times or on a recurring schedule.

    This tool is perfect for:
    - Daily/weekly routines: "Send me weather updates every morning", "Generate weekly reports"
    - Reminders and notifications: "Remind me about meetings", "Alert me about deadlines"
    - Automated content delivery: "Email me news headlines daily", "Send me stock updates"
    - Regular maintenance tasks: "Clean up old files weekly", "Backup data monthly"
    - Personal assistants: "Wake me up with motivational quotes", "Text me reminders"

    ## When to Use This Tool

    Use this tool when users ask for:
    - "Remind me to..." or "Send me..." with a time component
    - "Every morning/day/week..." recurring tasks
    - "At 8am..." or specific time requests
    - Automated reports, summaries, or updates
    - Any task that should happen repeatedly or at a future time

    ## When NOT to Use This Tool

    Don't use this tool for:
    - One-time tasks you can do immediately ("What's the weather now?")
    - Tasks requiring immediate action ("Call 911")
    - Complex multi-step workflows (use todo tools first to plan)

    Args:
        agent_instructions: Clear instructions for what the agent should do when scheduled.
            Be specific about the task and expected output.
            Examples:
            - "Send a friendly good morning text with weather and news summary"
            - "Generate a daily report of completed tasks and email it"
            - "Check for overdue items and send reminder notifications"

        schedule_config: When and how often to run the task:
            {
                "type": "once" | "cron",
                "when": "ISO datetime string" | "cron expression"
            }

            Common patterns:
            - Daily at 8 AM: {"type": "cron", "when": "0 8 * * *"}
            - Every Monday 9 AM: {"type": "cron", "when": "0 9 * * 1"}
            - Weekdays at 5 PM: {"type": "cron", "when": "0 17 * * 1-5"}
            - One-time tomorrow 2 PM: {"type": "once", "when": "2024-01-16T14:00:00"}

    Returns:
        Dictionary with task details including job_id, status, and next run time

    Examples:
        # Morning news delivery
        agent_instructions = "Text me a summary of headlines from New Yorker, Al Jazeera and Russia Today"
        schedule_config = {"type": "cron", "when": "0 8 * * *"}  # 8 AM daily

        # Wake up call
        agent_instructions = "Call me and give me a motivational morning message with weather update"
        schedule_config = {"type": "cron", "when": "0 7 * * *"}  # 7 AM daily

        # Weekly report
        agent_instructions = "Generate and email a summary of this week's completed tasks"
        schedule_config = {"type": "cron", "when": "0 9 * * 5"}  # Friday 9 AM
    """
    # Get the scheduling service from the app
    from quart import current_app

    scheduling_service = current_app.extensions.get("scheduling")
    if not scheduling_service:
        raise RuntimeError("Scheduling service not available")

    # Get conversation ID from context
    conversation_id = ctx.deps.get("conversation_id")
    if not conversation_id:
        raise ValueError("Conversation ID not found in context")

    # Generate unique task ID
    task_id = uuid.uuid4()

    # Schedule the task
    job_id = await scheduling_service.schedule_agent_execution(
        task_id=task_id,
        conversation_id=conversation_id,
        agent_instructions=agent_instructions,
        schedule_config=schedule_config,
        max_retries=3,
    )

    return {
        "status": "success",
        "job_id": job_id,
        "task_id": str(task_id),
        "message": f"Task scheduled successfully with job ID: {job_id}",
        "scheduled_for": schedule_config.get("when"),
        "type": schedule_config.get("type"),
    }
