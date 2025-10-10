"""create_separated_scheduled_tasks_table

Revision ID: 9876b3e19398
Revises: eb89cf1bd63d
Create Date: 2025-09-29 18:36:59.732007

"""
from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9876b3e19398'
down_revision: Union[str, Sequence[str], None] = 'eb89cf1bd63d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create scheduled_tasks table with separated schedule_type and schedule_config
    op.create_table('scheduled_tasks',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('job_id', sa.String(255), nullable=False),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('agent_instructions', sa.Text(), nullable=False),
        sa.Column('schedule_type', sa.String(20), nullable=False),
        sa.Column('schedule_config', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('interactive', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_run', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )

    # Create indexes
    op.create_index('ix_scheduled_tasks_job_id', 'scheduled_tasks', ['job_id'], unique=True)
    op.create_index('ix_scheduled_tasks_conversation_id', 'scheduled_tasks', ['conversation_id'], unique=False)

    # Create apscheduler_jobs table
    op.create_table('apscheduler_jobs',
        sa.Column('id', sa.String(191), nullable=False),
        sa.Column('next_run_time', sa.Float(), nullable=True),
        sa.Column('job_state', sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_apscheduler_jobs_next_run_time', 'apscheduler_jobs', ['next_run_time'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop APScheduler table if it exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'apscheduler_jobs' in inspector.get_table_names():
        op.drop_index('ix_apscheduler_jobs_next_run_time', table_name='apscheduler_jobs')
        op.drop_table('apscheduler_jobs')

    op.drop_index('ix_scheduled_tasks_conversation_id', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_job_id', table_name='scheduled_tasks')
    op.drop_table('scheduled_tasks')
