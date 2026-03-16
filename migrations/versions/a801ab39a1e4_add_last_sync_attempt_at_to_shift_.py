"""add last_sync_attempt_at to shift_schedule_entries

Revision ID: a801ab39a1e4
Revises: c978c2afbe91
Create Date: 2026-03-17 01:11:01.378967

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a801ab39a1e4'
down_revision = 'c978c2afbe91'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shift_schedule_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_sync_attempt_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('shift_schedule_entries', schema=None) as batch_op:
        batch_op.drop_column('last_sync_attempt_at')
