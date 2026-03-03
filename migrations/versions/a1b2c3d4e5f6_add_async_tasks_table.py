"""Add async_tasks table for background job queue

Revision ID: a1b2c3d4e5f6
Revises: dc3fa46ab193
Create Date: 2026-03-01 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'dc3fa46ab193'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('async_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('next_run_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_async_tasks_task_type', 'async_tasks', ['task_type'])
    op.create_index('ix_async_tasks_status', 'async_tasks', ['status'])
    op.create_index(
        'ix_async_tasks_pending_run',
        'async_tasks',
        ['status', 'next_run_at'],
    )


def downgrade():
    op.drop_index('ix_async_tasks_pending_run', table_name='async_tasks')
    op.drop_index('ix_async_tasks_status', table_name='async_tasks')
    op.drop_index('ix_async_tasks_task_type', table_name='async_tasks')
    op.drop_table('async_tasks')
