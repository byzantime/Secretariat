"""Database models for scheduled agent tasks."""

from datetime import datetime
from typing import Any
from typing import Dict
from typing import Optional
from uuid import UUID

from sqlalchemy import JSON
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.modules.database import Base


class ScheduledTask(Base):
    """Scheduled task model for database storage."""

    __tablename__ = "scheduled_tasks"

    id = Column(String(36), primary_key=True)
    job_id = Column(String(255), unique=True, nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    agent_instructions = Column(Text, nullable=False)
    schedule_config = Column(
        JSON, nullable=False
    )  # {type: "once"|"cron"|"interval", when: "..."}
    status = Column(
        String(50), nullable=False, default="pending"
    )  # pending, running, completed, failed
    failure_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    # Task configuration
    interactive = Column(
        Boolean, nullable=True, default=True
    )  # Whether task supports user interaction/responses

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_run = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<ScheduledTask(id={self.id}, job_id={self.job_id}, status={self.status})>"
        )

    @staticmethod
    async def get_by_id(
        session: AsyncSession, task_id: UUID
    ) -> Optional["ScheduledTask"]:
        """Get scheduled task by ID."""
        result = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_task(
        session: AsyncSession,
        task_id: UUID,
        job_id: str,
        conversation_id: UUID,
        agent_instructions: str,
        schedule_config: Dict[str, Any],
        interactive: bool = True,
    ) -> "ScheduledTask":
        """Create a new scheduled task."""
        task = ScheduledTask(
            id=task_id,
            job_id=job_id,
            conversation_id=conversation_id,
            agent_instructions=agent_instructions,
            schedule_config=schedule_config,
            interactive=interactive,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

    async def update_status(
        self,
        session: AsyncSession,
        status: str,
        error_message: Optional[str] = None,
        last_run: Optional[datetime] = None,
    ):
        """Update task status and related fields."""
        self.status = status
        if error_message is not None:
            self.error_message = error_message
        if last_run is not None:
            self.last_run = last_run

        if status == "failed":
            self.failure_count += 1

        await session.commit()

    async def increment_failure_count(self, session: AsyncSession):
        """Increment failure count."""
        self.failure_count += 1
        await session.commit()

    async def delete(self, session: AsyncSession):
        """Delete scheduled task."""
        await session.delete(self)
        await session.commit()
