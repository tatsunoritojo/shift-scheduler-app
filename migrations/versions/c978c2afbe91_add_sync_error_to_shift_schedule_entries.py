"""add sync_error to shift_schedule_entries

Revision ID: c978c2afbe91
Revises: d4e5f6a7b8c9
Create Date: 2026-03-17 00:33:13.961393

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c978c2afbe91'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shift_schedule_entries', sa.Column('sync_error', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('shift_schedule_entries', schema=None) as batch_op:
        batch_op.drop_column('sync_error')
