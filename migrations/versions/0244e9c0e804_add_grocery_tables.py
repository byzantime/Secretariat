"""add_grocery_tables

Revision ID: 0244e9c0e804
Revises: 9876b3e19398
Create Date: 2025-10-02 00:16:59.299797

"""
from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0244e9c0e804'
down_revision: Union[str, Sequence[str], None] = '9876b3e19398'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create grocery_items table
    op.create_table(
        'grocery_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('unit_type', sa.String(50), nullable=True),
        sa.Column('typical_quantity', sa.Float(), nullable=True),
        sa.Column('base_frequency_days', sa.Integer(), nullable=True),
        sa.Column('frequency_adjustment_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_purchased_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id', 'name', name='uq_grocery_items_user_name')
    )
    op.create_index('idx_grocery_items_user', 'grocery_items', ['user_id'])
    op.create_index('idx_grocery_items_last_purchased', 'grocery_items', ['last_purchased_date'])

    # Create grocery_orders table
    op.create_table(
        'grocery_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('supermarket', sa.String(100), nullable=False),
        sa.Column('order_date', sa.Date(), nullable=False),
        sa.Column('total_cost', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    op.create_index('idx_grocery_orders_user', 'grocery_orders', ['user_id'])
    op.create_index('idx_grocery_orders_date', 'grocery_orders', ['order_date'])

    # Create order_items table
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=True),
        sa.Column('total_price', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['grocery_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['grocery_items.id'])
    )
    op.create_index('idx_order_items_order', 'order_items', ['order_id'])
    op.create_index('idx_order_items_item', 'order_items', ['item_id'])

    # Create shopping_list table
    op.create_table(
        'shopping_list',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('quantity_needed', sa.Float(), nullable=True),
        sa.Column('urgency', sa.String(20), nullable=False, server_default='normal'),
        sa.Column('added_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['item_id'], ['grocery_items.id']),
        sa.UniqueConstraint('user_id', 'item_id', name='uq_shopping_list_user_item')
    )
    op.create_index('idx_shopping_list_user', 'shopping_list', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_index('idx_shopping_list_user', table_name='shopping_list')
    op.drop_table('shopping_list')

    op.drop_index('idx_order_items_item', table_name='order_items')
    op.drop_index('idx_order_items_order', table_name='order_items')
    op.drop_table('order_items')

    op.drop_index('idx_grocery_orders_date', table_name='grocery_orders')
    op.drop_index('idx_grocery_orders_user', table_name='grocery_orders')
    op.drop_table('grocery_orders')

    op.drop_index('idx_grocery_items_last_purchased', table_name='grocery_items')
    op.drop_index('idx_grocery_items_user', table_name='grocery_items')
    op.drop_table('grocery_items')
