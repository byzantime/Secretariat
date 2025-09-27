"""Scheduling service using APScheduler with PostgreSQL backend."""

from datetime import datetime
from typing import Any
from typing import Dict
from uuid import UUID

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from quart import current_app

from src.models.scheduled_task import ScheduledTask


class SchedulingService:
    """Service for scheduling agent tasks using APScheduler."""

    def __init__(self, app=None):
        self.scheduler = None
        self.db = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize scheduling service with Quart app."""
        self.db = app.extensions["database"]

        # Configure APScheduler with SQLite job store using sync engine
        jobstores = {
            "default": SQLAlchemyJobStore(
                engine=self.db.sync_engine,  # Use sync engine for APScheduler
                tablename="apscheduler_jobs",
            )
        }

        # Configure scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": True,  # Combine multiple executions
                "max_instances": 1,  # Only one instance per job
                "misfire_grace_time": 30,  # 30 seconds grace time
            },
            timezone=app.config.get("TIMEZONE", "UTC"),
            logger=app.logger,
        )

        # Start scheduler on app start, shutdown on app stop
        app.before_serving(self.start_scheduler)
        app.after_serving(self.shutdown_scheduler)

        app.extensions["scheduling"] = self
        app.logger.info("SchedulingService initialized")

    async def start_scheduler(self):
        """Start the APScheduler and restore pending jobs."""
        if self.scheduler and not self.scheduler.running:
            try:
                self.scheduler.start()
                current_app.logger.info("APScheduler started")

                # Restore pending jobs from database
                await self._restore_pending_jobs()

            except Exception as e:
                current_app.logger.error(f"Failed to start APScheduler: {e}")
                raise

    async def shutdown_scheduler(self):
        """Shutdown the APScheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            current_app.logger.info("APScheduler shutdown")

    async def _restore_pending_jobs(self):
        """Restore pending jobs from database to scheduler."""
        try:
            from sqlalchemy.future import select

            from src.models.scheduled_task import ScheduledTask

            async with self.db.session_factory() as session:
                # Get all pending tasks
                result = await session.execute(
                    select(ScheduledTask).where(ScheduledTask.status == "pending")  # type: ignore
                )
                pending_tasks = result.scalars().all()

                current_app.logger.info(
                    f"Found {len(pending_tasks)} pending tasks to restore"
                )

                for task in pending_tasks:
                    try:
                        # Check if job already exists in scheduler
                        if self.scheduler:
                            existing_job = self.scheduler.get_job(task.job_id)
                            if existing_job:
                                current_app.logger.debug(
                                    f"Job {task.job_id} already exists in scheduler"
                                )
                                continue

                        # Recreate the trigger based on schedule config
                        if task.schedule_config["type"] == "once":
                            run_date = datetime.fromisoformat(
                                task.schedule_config["when"]
                            )
                            # Skip if the scheduled time has already passed
                            if run_date < datetime.now():
                                current_app.logger.warning(
                                    f"Task {task.id} scheduled for past time"
                                    f" {run_date}, marking as missed"
                                )
                                await task.update_status(
                                    session,
                                    "failed",
                                    error_message=(
                                        "Scheduled time passed before execution"
                                    ),
                                )
                                continue

                            trigger = DateTrigger(run_date=run_date)
                        elif task.schedule_config["type"] == "cron":
                            trigger = CronTrigger(
                                year=task.schedule_config.get("year"),
                                month=task.schedule_config.get("month"),
                                day=task.schedule_config.get("day"),
                                week=task.schedule_config.get("week"),
                                day_of_week=task.schedule_config.get("day_of_week"),
                                hour=task.schedule_config.get("hour"),
                                minute=task.schedule_config.get("minute"),
                                second=task.schedule_config.get("second"),
                                start_date=task.schedule_config.get("start_date"),
                                end_date=task.schedule_config.get("end_date"),
                            )
                        elif task.schedule_config["type"] == "interval":
                            trigger = IntervalTrigger(
                                weeks=task.schedule_config.get("weeks", 0),
                                days=task.schedule_config.get("days", 0),
                                hours=task.schedule_config.get("hours", 0),
                                minutes=task.schedule_config.get("minutes", 0),
                                seconds=task.schedule_config.get("seconds", 0),
                                start_date=task.schedule_config.get("start_date"),
                                end_date=task.schedule_config.get("end_date"),
                            )
                        else:
                            current_app.logger.error(
                                f"Unknown schedule type for task {task.id}:"
                                f" {task.schedule_config['type']}"
                            )
                            continue

                        # Recreate the job in the scheduler
                        if self.scheduler:
                            self.scheduler.add_job(
                                func=SchedulingService._execute_scheduled_agent,
                                trigger=trigger,
                                id=task.job_id,
                                args=[
                                    task.id,
                                    task.conversation_id,
                                    task.agent_instructions,
                                    3,
                                    task.interactive,
                                ],
                                name=(
                                    f"{task.job_id}: {task.agent_instructions[:50]}..."
                                ),
                                replace_existing=True,
                            )

                        current_app.logger.info(
                            f"Restored job {task.job_id} for task {task.id}"
                        )

                    except Exception as e:
                        current_app.logger.error(
                            f"Failed to restore job {task.job_id}: {e}"
                        )
                        # Don't fail the entire restoration process for one bad job
                        continue

        except Exception as e:
            current_app.logger.error(f"Failed to restore pending jobs: {e}")
            # Don't raise - we want the scheduler to start even if restoration fails

    async def schedule_agent_execution(
        self,
        task_id: UUID,
        conversation_id: UUID,
        agent_instructions: str,
        schedule_config: Dict[str, Any],
        interactive: bool = True,
        max_retries: int = 3,
    ) -> str:
        """Schedule an agent execution task.

        Args:
            task_id: Unique task identifier
            conversation_id: Conversation context
            agent_instructions: Instructions for the agent
            schedule_config: Scheduling configuration
                - type: "once", "cron", or "interval"
                - For "once": when: datetime string
                - For "cron": year/month/day/week/day_of_week/hour/minute/second/start_date/end_date parameters
                - For "interval": weeks/days/hours/minutes/seconds/start_date/end_date parameters
            interactive: Whether this task should support user interaction/responses (default: True)
            max_retries: Maximum retry attempts

        Returns:
            APScheduler job ID
        """
        # Create trigger based on schedule type
        if schedule_config["type"] == "once":
            trigger = DateTrigger(
                run_date=datetime.fromisoformat(schedule_config["when"])
            )
        elif schedule_config["type"] == "cron":
            trigger = CronTrigger(
                year=schedule_config.get("year"),
                month=schedule_config.get("month"),
                day=schedule_config.get("day"),
                week=schedule_config.get("week"),
                day_of_week=schedule_config.get("day_of_week"),
                hour=schedule_config.get("hour"),
                minute=schedule_config.get("minute"),
                second=schedule_config.get("second"),
                start_date=schedule_config.get("start_date"),
                end_date=schedule_config.get("end_date"),
            )
        elif schedule_config["type"] == "interval":
            trigger = IntervalTrigger(
                weeks=schedule_config.get("weeks"),
                days=schedule_config.get("days"),
                hours=schedule_config.get("hours"),
                minutes=schedule_config.get("minutes"),
                seconds=schedule_config.get("seconds"),
                start_date=schedule_config.get("start_date"),
                end_date=schedule_config.get("end_date"),
            )
        else:
            raise ValueError(f"Unsupported schedule type: {schedule_config['type']}")

        # Create job
        self.scheduler.add_job(
            func=SchedulingService._execute_scheduled_agent,
            trigger=trigger,
            id=str(task_id),
            args=[
                task_id,
                conversation_id,
                agent_instructions,
                max_retries,
                interactive,
            ],
            name=f"{agent_instructions[:50]}...",
            replace_existing=True,
        )

        # Store task in database
        async with self.db.session_factory() as session:
            await ScheduledTask.create_task(
                session=session,
                task_id=task_id,
                job_id=str(task_id),
                conversation_id=conversation_id,
                agent_instructions=agent_instructions,
                schedule_config=schedule_config,
                interactive=interactive,
            )

        current_app.logger.info(f"Scheduled agent task {task_id} with job ID {task_id}")
        return task_id

    @staticmethod
    async def _execute_scheduled_agent(
        task_id: UUID,
        conversation_id: UUID,
        agent_instructions: str,
        max_retries: int,
        interactive: bool,
    ):
        """Execute a scheduled agent task."""
        current_app.logger.info(f"Executing scheduled agent task {task_id}")

        try:
            # Update task status to running
            db = current_app.extensions["database"]
            async with db.session_factory() as session:
                task = await ScheduledTask.get_by_id(session, task_id)
                if task is not None:
                    await task.update_status(
                        session, "running", last_run=datetime.now()
                    )

            # Get LLM service
            llm_service = current_app.extensions["llm"]

            # Create a temporary agent for execution
            # This will use the same model and configuration as the main agent
            temp_agent = llm_service.agent

            if interactive:
                # Interactive mode: use streaming with full event emission
                await llm_service.execute_agent_stream(
                    agent_instructions=agent_instructions,
                    message_history=[],
                    deps={},
                    emit_events=True,  # Interactive mode should emit events
                    store_result=True,  # Agent output will be added to history.
                )
            else:
                # Non-interactive mode: use batch execution
                result = await temp_agent.run(
                    user_prompt=agent_instructions,
                    message_history=[],
                    deps={},
                )
                # Store the result in conversation
                conversation.store_run_result(result)

            # Update task status to completed
            async with db.session_factory() as session:
                task = await ScheduledTask.get_by_id(session, task_id)
                if task:
                    await task.update_status(session, "completed")

            # Notify user of successful completion
            event_handler = current_app.extensions["event_handler"]
            await event_handler.emit_to_services(
                "status.update",
                {"message": "Scheduled task completed successfully"},
            )

            current_app.logger.info(
                f"Successfully executed scheduled agent task {task_id}"
            )

        except Exception as e:
            current_app.logger.error(
                f"Error executing scheduled agent task {task_id}: {str(e)}"
            )

            # Update task status and handle retries
            async with db.session_factory() as session:
                task = await ScheduledTask.get_by_id(session, task_id)
                if task is not None:
                    failure_count = task.failure_count or 0
                    if failure_count >= max_retries:
                        await task.update_status(
                            session, "failed", error_message=str(e)
                        )
                        current_app.logger.error(
                            f"Task {task_id} failed permanently after"
                            f" {max_retries} retries"
                        )
                        # Notify user of permanent failure
                        event_handler = current_app.extensions["event_handler"]
                        await event_handler.emit_to_services(
                            "status.update",
                            {
                                "message": (
                                    "Scheduled task failed permanently after"
                                    f" {max_retries} retries: {str(e)}"
                                )
                            },
                        )
                    else:
                        await task.update_status(
                            session, "pending", error_message=str(e)
                        )
                        current_app.logger.warning(
                            f"Task {task_id} failed, will retry (attempt"
                            f" {task.failure_count + 1}/{max_retries})"
                        )

            # Re-raise to let APScheduler handle retry logic
            raise
