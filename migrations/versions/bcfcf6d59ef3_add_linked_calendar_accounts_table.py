"""add linked_calendar_accounts table

Revision ID: bcfcf6d59ef3
Revises: a801ab39a1e4
Create Date: 2026-03-17 02:07:18.736792

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bcfcf6d59ef3'
down_revision = 'a801ab39a1e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('linked_calendar_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('google_email', sa.String(length=255), nullable=False),
    sa.Column('google_sub', sa.String(length=255), nullable=False),
    sa.Column('refresh_token', sa.String(length=512), nullable=False),
    sa.Column('scopes', sa.Text(), nullable=True),
    sa.Column('label', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'google_sub', name='uq_linked_cal_user_google')
    )


def downgrade():
    op.drop_table('linked_calendar_accounts')
