"""Add invite_code and invite_code_enabled to organizations

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('organizations', sa.Column('invite_code', sa.String(32), nullable=True))
    op.add_column('organizations', sa.Column('invite_code_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    # SQLite does not enforce unique constraints added via ALTER; skip for SQLite.
    # Production (PostgreSQL) will enforce via the model's UniqueConstraint.


def downgrade():
    op.drop_column('organizations', 'invite_code_enabled')
    op.drop_column('organizations', 'invite_code')
