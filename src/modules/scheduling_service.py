"""Scheduling service using APScheduler with PostgreSQL backend."""

from datetime import datetime
from typing import Any
from typing import Dict
from uuid import UUID

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from quart import current_app

from src.models.scheduled_task import ScheduledTask
from src.routes import _broadcast_event


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

        # Configure APScheduler with PostgreSQL job store using sync engine
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
        """Start the APScheduler."""
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            current_app.logger.info("APScheduler started")

    async def shutdown_scheduler(self):
        """Shutdown the APScheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            current_app.logger.info("APScheduler shutdown")

    async def schedule_agent_execution(
        self,
        task_id: UUID,
        conversation_id: UUID,
        agent_instructions: str,
        schedule_config: Dict[str, Any],
        max_retries: int = 3,
    ) -> str:
        """Schedule an agent execution task.

        Args:
            task_id: Unique task identifier
            conversation_id: Conversation context
            agent_instructions: Instructions for the agent
            schedule_config: Scheduling configuration
                - type: "once" or "cron"
                - when: datetime string or cron expression
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
            trigger = CronTrigger.from_crontab(schedule_config["when"])
        else:
            raise ValueError(f"Unsupported schedule type: {schedule_config['type']}")

        # Create job
        job_id = f"agent_task_{task_id}"

        self.scheduler.add_job(
            func=SchedulingService._execute_scheduled_agent,
            trigger=trigger,
            id=job_id,
            args=[
                task_id,
                conversation_id,
                agent_instructions,
                max_retries,
            ],
            name=f"Agent execution: {agent_instructions[:50]}...",
            replace_existing=True,
        )

        # Store task in database
        async with self.db.session_factory() as session:
            await ScheduledTask.create_task(
                session=session,
                task_id=task_id,
                job_id=job_id,
                conversation_id=conversation_id,
                agent_instructions=agent_instructions,
                schedule_config=schedule_config,
            )

        current_app.logger.info(f"Scheduled agent task {task_id} with job ID {job_id}")
        return job_id

    @staticmethod
    async def _execute_scheduled_agent(
        task_id: UUID,
        conversation_id: UUID,
        agent_instructions: str,
        max_retries: int,
    ):
        """Execute a scheduled agent task."""
        current_app.logger.info(f"Executing scheduled agent task {task_id}")

        try:
            # Get database from app extensions
            db = current_app.extensions["database"]

            # Update task status to running
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

            # Get conversation manager
            conversation_manager = current_app.extensions["conversation_manager"]
            conversation = await conversation_manager.get_conversation(conversation_id)

            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Get conversation history
            message_history = conversation.get_pydantic_messages(
                last_n=llm_service.max_history
            )

            # Execute the agent
            deps = {"conversation_id": conversation_id, "conversation": conversation}

            result = await temp_agent.run(
                user_prompt=agent_instructions,
                message_history=message_history,
                deps=deps,
            )

            # Store the result in conversation
            conversation.store_run_result(result)

            # Update task status to completed
            async with db.session_factory() as session:
                task = await ScheduledTask.get_by_id(session, task_id)
                if task:
                    await task.update_status(session, "completed")

            # Notify user of successful completion
            await _broadcast_event(
                "scheduled_task_completed", "Scheduled task completed successfully"
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
                    if task.failure_count >= max_retries:
                        await task.update_status(
                            session, "failed", error_message=str(e)
                        )
                        current_app.logger.error(
                            f"Task {task_id} failed permanently after"
                            f" {max_retries} retries"
                        )
                        # Notify user of permanent failure
                        await _broadcast_event(
                            "scheduled_task_failed",
                            "Scheduled task failed permanently after"
                            f" {max_retries} retries: {str(e)}",
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

    async def _job_executed(self, event):
        """Handle successful job execution."""
        current_app.logger.debug(f"Job {event.job_id} executed successfully")

    async def _job_error(self, event):
        """Handle job execution errors."""
        current_app.logger.error(f"Job {event.job_id} failed: {event.exception}")

    async def _job_added(self, event):
        """Handle job added event."""
        current_app.logger.info(f"Job {event.job_id} added to scheduler")

    async def _job_removed(self, event):
        """Handle job removed event."""
        current_app.logger.info(f"Job {event.job_id} removed from scheduler")

    async def _job_missed(self, event):
        """Handle job missed event."""
        current_app.logger.warning(f"Job {event.job_id} missed its scheduled run time")

    async def get_session(self):
        """Get database session context manager."""
        return self.db.session_factory()
