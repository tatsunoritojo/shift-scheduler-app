"""add announcement_text to shift_periods

Revision ID: d299d33dbee7
Revises: f3a61e8618bf
Create Date: 2026-04-29 23:02:03.546387

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd299d33dbee7'
down_revision = 'f3a61e8618bf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shift_periods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('announcement_text', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('shift_periods', schema=None) as batch_op:
        batch_op.drop_column('announcement_text')
