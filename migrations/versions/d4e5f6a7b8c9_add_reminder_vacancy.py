"""Add reminder, vacancy_request, vacancy_candidate, shift_change_log tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('reminder_type', sa.String(length=30), nullable=False),
        sa.Column('reference_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reminder_type', 'reference_id', 'user_id', name='uq_reminder_type_ref_user'),
    )

    op.create_table('vacancy_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_entry_id', sa.Integer(), nullable=False),
        sa.Column('original_user_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('accepted_by', sa.Integer(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['original_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['schedule_entry_id'], ['shift_schedule_entries.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('vacancy_candidates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vacancy_request_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_token', sa.String(length=512), nullable=True),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vacancy_request_id'], ['vacancy_requests.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('response_token'),
        sa.UniqueConstraint('vacancy_request_id', 'user_id', name='uq_vacancy_candidate_request_user'),
    )

    op.create_table('shift_change_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_entry_id', sa.Integer(), nullable=False),
        sa.Column('vacancy_request_id', sa.Integer(), nullable=True),
        sa.Column('change_type', sa.String(length=30), nullable=False),
        sa.Column('original_user_id', sa.Integer(), nullable=False),
        sa.Column('new_user_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('performed_by', sa.Integer(), nullable=False),
        sa.Column('performed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['new_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['original_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['schedule_entry_id'], ['shift_schedule_entries.id'], ),
        sa.ForeignKeyConstraint(['vacancy_request_id'], ['vacancy_requests.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('shift_change_logs')
    op.drop_table('vacancy_candidates')
    op.drop_table('vacancy_requests')
    op.drop_table('reminders')
