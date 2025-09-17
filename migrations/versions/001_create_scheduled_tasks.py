"""Add scheduled_tasks table for agent scheduling

Revision ID: 001_create_scheduled_tasks
Revises:
Create Date: 2025-01-17 10:00:00.000000

"""

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_create_scheduled_tasks"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create scheduled_tasks table
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.String(255), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_instructions", sa.Text(), nullable=False),
        sa.Column("schedule_config", postgresql.JSONB(), nullable=False),
        sa.Column("agent_config", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("failure_count", sa.Integer(), nullable=False, default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("last_run", sa.DateTime(), nullable=True),
        sa.Column("next_run", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )

    # Create indexes for performance
    op.create_index(
        "ix_scheduled_tasks_conversation_id", "scheduled_tasks", ["conversation_id"]
    )
    op.create_index("ix_scheduled_tasks_status", "scheduled_tasks", ["status"])
    op.create_index("ix_scheduled_tasks_next_run", "scheduled_tasks", ["next_run"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_scheduled_tasks_next_run", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_status", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_conversation_id", table_name="scheduled_tasks")

    # Drop table
    op.drop_table("scheduled_tasks")
