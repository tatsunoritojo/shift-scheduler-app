"""add is_archived and archived_at to shift_periods

Revision ID: f3a61e8618bf
Revises: e7f8a9b0c1d2
Create Date: 2026-04-26 01:00:29.639907

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a61e8618bf'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shift_periods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('shift_periods', schema=None) as batch_op:
        batch_op.drop_column('archived_at')
        batch_op.drop_column('is_archived')
