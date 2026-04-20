"""add member level and attendance

Revision ID: e7f8a9b0c1d2
Revises: bcfcf6d59ef3
Create Date: 2026-04-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'bcfcf6d59ef3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization_members', schema=None) as batch_op:
        batch_op.add_column(sa.Column('level_key', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('min_attendance_count_per_week', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('min_attendance_hours_per_week', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization_members', schema=None) as batch_op:
        batch_op.drop_column('min_attendance_hours_per_week')
        batch_op.drop_column('min_attendance_count_per_week')
        batch_op.drop_column('level_key')
