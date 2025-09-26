"""Scheduling tools for agent execution."""

import uuid
from typing import Any
from typing import Dict

from apscheduler.jobstores.base import JobLookupError
from pydantic_ai import RunContext
from quart import current_app

from src.models.schedule_config import ScheduleConfig
from src.models.schedule_config import schedule_config_to_dict


async def setup_automation(
    ctx: RunContext[Dict[str, Any]],
    agent_instructions: str,
    schedule_config: ScheduleConfig,
    interactive: bool = True,
) -> Dict[str, Any]:
    """Schedule automated agent tasks using three distinct timing approaches.

    Use this tool to set up automated execution of agent tasks at specific times or recurring intervals.
    The key is choosing the right schedule type for your timing pattern.

    ## Quick Decision Guide

    Ask yourself: "When should this task run?"

    - **One specific time** → Use "once"
    - **Calendar pattern** (daily, weekly, monthly) → Use "cron"
    - **Time interval pattern** (every X hours/days) → Use "interval"

    ## Schedule Types: Critical Differences

    **"once" (DateTrigger)**: Execute exactly once at a specific moment
    - Purpose: One-time future events
    - Use for: Appointments, deadlines, reminders for specific dates
    - Examples: "Remind me about the meeting tomorrow at 2 PM", "Send birthday wishes on December 25th at 9 AM"

    **"cron" (CronTrigger)**: Execute on calendar-based recurring patterns
    - Purpose: Calendar-aligned schedules (think business calendar)
    - Use for: Daily routines, weekly reports, monthly tasks, business hours
    - Examples: "Every Monday at 9 AM", "First day of every month", "Weekdays at 5 PM"
    - ✅ **Can express**: "Every Tuesday", "Daily at 8 AM", "Monthly on the 15th"
    - ❌ **Cannot express**: "Every other Tuesday", "Every 3 days", "Every 72 hours"

    **"interval" (IntervalTrigger)**: Execute at fixed time intervals
    - Purpose: Time-duration based repetition from a starting point
    - Use for: Monitoring, polling, any "every X time units" pattern
    - Examples: "Every 2 hours", "Every 30 minutes", "Every 3 days starting now"
    - ✅ **Can express**: "Every other Friday" (start_date + 2 weeks), "Every 72 hours", "Every 3 days"
    - 🎯 **CRITICAL**: Use this for patterns cron cannot handle like "every other week"

    ## When to Use This Tool

    Use when users request:
    - "Remind me to..." or "Send me..." with timing
    - "Every [time period]..." recurring tasks
    - "At [specific time]..." scheduled tasks
    - Automated reports, summaries, or notifications
    - Background monitoring or polling tasks

    ## When NOT to Use This Tool

    Don't use for:
    - Immediate tasks ("What's the weather now?")
    - Emergency actions ("Call 911")
    - Complex workflows (break into steps first)

    Examples:
        # ONE-TIME: Specific moment (use "once")
        agent_instructions = "Send me a birthday reminder"
        schedule_config = OnceSchedule(type="once", when="2024-12-25T09:00:00")

        # CALENDAR-BASED: Business routine (use "cron")
        agent_instructions = "Send morning briefing with calendar and priorities"
        schedule_config = CronSchedule(type="cron", day_of_week="mon-fri", hour=8, minute=30)

        # TIME-INTERVAL: Regular monitoring (use "interval")
        agent_instructions = "Check system health and alert if issues found"
        schedule_config = IntervalSchedule(type="interval", hours=2)

        # CALENDAR-BASED: Weekly report (use "cron")
        agent_instructions = "Generate weekly task summary and email it"
        schedule_config = CronSchedule(type="cron", day_of_week="fri", hour=17, minute=0)

        # TIME-INTERVAL: High-frequency updates (use "interval")
        agent_instructions = "Update dashboard with latest metrics"
        schedule_config = IntervalSchedule(type="interval", minutes=15)

        # ⚠️ CRITICAL EXAMPLE: "Every other Thursday" - MUST use interval, not cron!
        agent_instructions = "Send bi-weekly team update"
        schedule_config = IntervalSchedule(type="interval", weeks=2, start_date="2025-09-25T10:00:00")
        # Why interval? Cron cannot express "every other" patterns - only interval can!

        # ⚠️ WRONG APPROACH: Don't try this with cron - it won't work for "every other"
        schedule_config = CronSchedule(type="cron", day_of_week="thu")  # This is EVERY Thursday, not every other!

    Returns:
        Dictionary with task details including job_id, status, and next run time

    """
    # Get conversation ID from context
    conversation_id = ctx.deps.get("conversation_id")
    if not conversation_id:
        raise ValueError("Conversation ID not found in context")

    # Generate unique task ID
    task_id = uuid.uuid4()

    # Convert Pydantic model to dict for compatibility with existing code
    schedule_config_dict = schedule_config_to_dict(schedule_config)

    # Schedule the task
    scheduling_service = current_app.extensions["scheduling"]
    job_id = await scheduling_service.schedule_agent_execution(
        task_id=task_id,
        conversation_id=conversation_id,
        agent_instructions=agent_instructions,
        schedule_config=schedule_config_dict,
        interactive=interactive,
        max_retries=3,
    )

    # Determine scheduled_for based on type
    if schedule_config.type == "interval":
        scheduled_for = getattr(schedule_config, "start_date", None) or "interval"
    else:
        scheduled_for = getattr(schedule_config, "when", "unknown")

    return {
        "status": "success",
        "job_id": job_id,
        "task_id": str(task_id),
        "message": f"Task scheduled successfully with job ID: {job_id}",
        "scheduled_for": scheduled_for,
        "type": schedule_config.type,
    }


async def automations_list(ctx: RunContext[Dict[str, Any]]) -> str:
    """Use this tool to list current automated tasks.

    This tool should be used proactively to check what automated tasks are currently scheduled.
    You should make use of this tool when:
    - Users ask about their scheduled tasks, reminders, or automations
    - Before setting up new automations to avoid duplicates
    - When reviewing what tasks the agent will perform automatically
    - To check the status of recurring tasks and their next run times

    Usage:
    - This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like "input" or "empty". LEAVE IT BLANK.
    - Returns a list of scheduled tasks with their status, schedule, and next run time
    - Use this information to understand what automations are active
    - If no tasks are scheduled, a simple message will be returned
    """
    current_app.logger.info("🔧 TOOL CALLED: automations_list")

    # Get jobs from APScheduler
    scheduling_service = current_app.extensions["scheduling"]
    jobs = scheduling_service.scheduler.get_jobs()

    if not jobs:
        current_app.logger.info("No jobs are currently scheduled.")
        return "No jobs are currently scheduled."

    current_app.logger.debug(f"Scheduled jobs: {jobs}")

    # Format jobs as CSV with headers
    output = "job_id,next_run_time,schedule_type,description\n"

    for job in jobs:
        # Extract task ID from job ID (format: "agent_task_{task_id}")
        task_id = (
            job.id.replace("agent_task_", "")
            if job.id.startswith("agent_task_")
            else job.id
        )

        # Get next run time
        next_run_time = str(job.next_run_time) if job.next_run_time else "N/A"

        # Determine schedule type from trigger
        schedule_type = "unknown"
        if hasattr(job.trigger, "__class__"):
            trigger_name = job.trigger.__class__.__name__
            if trigger_name == "DateTrigger":
                schedule_type = "once"
            elif trigger_name == "CronTrigger":
                schedule_type = "cron"
            elif trigger_name == "IntervalTrigger":
                schedule_type = "interval"

        # Get description from job name, remove the "Agent execution: " prefix
        description = job.name or "Unknown task"
        if description.startswith("Agent execution: "):
            description = description[17:]  # Remove "Agent execution: " prefix
        description = description.replace(",", ";")  # Escape commas for CSV

        output += f"{task_id},{next_run_time},{schedule_type},{description}\n"

    current_app.logger.info(output)
    return output.strip()


async def delete_automation(ctx: RunContext[Dict[str, Any]], task_id: str) -> str:
    """Delete an automated task by its task ID.

    Use this tool to delete/cancel scheduled automated tasks.  Use the
    automations_list tool to get the task ID for a given task.

    Args:
        task_id: The UUID string identifier of the task to delete. This can be obtained
                from the automations_list tool output (first column in CSV).

    Examples:
        # Delete a specific automation by its ID
        delete_automation(task_id="123e4567-e89b-12d3-a456-426614174000")
    """
    current_app.logger.info(f"🔧 TOOL CALLED: delete_automation with task_id={task_id}")
    scheduling_service = current_app.extensions["scheduling"]
    try:
        scheduling_service.scheduler.remove_job(f"agent_task_{task_id}")
        return f"Task with ID {task_id} deleted successfully"
    except JobLookupError:
        return f"Task with ID {task_id} not found or could not be deleted"
