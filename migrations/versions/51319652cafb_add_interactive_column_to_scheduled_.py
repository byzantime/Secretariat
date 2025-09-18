"""Add interactive column to scheduled_tasks

Revision ID: 51319652cafb
Revises: 001_create_scheduled_tasks
Create Date: 2025-09-18 10:34:21.262394

"""

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "51319652cafb"
down_revision: Union[str, Sequence[str], None] = "001_create_scheduled_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add interactive column to scheduled_tasks table."""
    op.add_column(
        "scheduled_tasks",
        sa.Column("interactive", sa.Boolean(), nullable=False, server_default="true"),
    )
    # Remove the server default since we want the default to be handled by the model
    op.alter_column("scheduled_tasks", "interactive", server_default=None)


def downgrade() -> None:
    """Remove interactive column from scheduled_tasks table."""
    op.drop_column("scheduled_tasks", "interactive")
