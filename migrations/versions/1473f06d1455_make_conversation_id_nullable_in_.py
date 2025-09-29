"""Make conversation_id nullable in scheduled_tasks

Revision ID: 1473f06d1455
Revises: f7c6b6e31ea4
Create Date: 2025-09-29 15:27:11.555349

"""
from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1473f06d1455'
down_revision: Union[str, Sequence[str], None] = 'f7c6b6e31ea4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Make conversation_id nullable in scheduled_tasks
    with op.batch_alter_table('scheduled_tasks', schema=None) as batch_op:
        batch_op.alter_column('conversation_id',
                              existing_type=sa.VARCHAR(length=36),
                              nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert conversation_id back to NOT NULL
    with op.batch_alter_table('scheduled_tasks', schema=None) as batch_op:
        batch_op.alter_column('conversation_id',
                              existing_type=sa.VARCHAR(length=36),
                              nullable=False)
