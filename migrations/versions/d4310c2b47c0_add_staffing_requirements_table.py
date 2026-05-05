"""add staffing_requirements table

Revision ID: d4310c2b47c0
Revises: d299d33dbee7
Create Date: 2026-05-05 11:03:14.421435

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4310c2b47c0'
down_revision = 'd299d33dbee7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'staffing_requirements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('required_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_staffing_org_day',
        'staffing_requirements',
        ['organization_id', 'day_of_week'],
    )


def downgrade():
    op.drop_index('ix_staffing_org_day', table_name='staffing_requirements')
    op.drop_table('staffing_requirements')
