"""Tests for Phase A': shift confirmation when approval process is disabled.

When approval_required=false, admins can transition draft → confirmed directly,
skipping pending_approval and approved.
"""

import pytest

from app.extensions import db
from app.models.approval import ApprovalHistory
from app.models.shift import ShiftSchedule
from app.services import organization_settings as org_settings


class TestConfirmDirect:
    """draft → confirmed (no approval step)."""

    def test_confirm_draft_directly_when_approval_off(
        self, client, auth, admin_user, period, schedule, org, db_session,
    ):
        # New org with no owner → approval_required defaults to false
        assert schedule.status == 'draft'
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule/confirm")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'confirmed'
        assert data['approved_by'] == admin_user.id
        assert data['confirmed_at'] is not None

    def test_confirm_records_audit(self, client, auth, admin_user, period, schedule, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/schedule/confirm")

        from app.models.audit_log import AuditLog
        logs = AuditLog.query.filter_by(action='SCHEDULE_CONFIRMED_DIRECT').all()
        assert len(logs) == 1
        assert logs[0].resource_id == schedule.id

    def test_confirm_records_history(self, client, auth, admin_user, period, schedule, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/schedule/confirm")

        history = ApprovalHistory.query.filter_by(schedule_id=schedule.id).all()
        assert len(history) == 1
        assert history[0].action == 'confirmed'


class TestSubmitBlockedWhenApprovalOff:
    """submit endpoint should 400 when approval is disabled."""

    def test_submit_blocked(self, client, auth, admin_user, period, schedule, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule/submit")
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'APPROVAL_DISABLED'


class TestApprovalFlowPreservedWhenOn:
    """When approval_required=true (owner exists), current 4-stage flow is intact."""

    def test_full_flow_intact(self, client, auth, admin_user, owner_user, period, schedule, db_session):
        # owner_user fixture auto-enables approval_required
        db_session.commit()

        # submit
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule/submit")
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'pending_approval'

        # approve
        auth.login_as(owner_user)
        resp = client.post(f"/api/owner/schedules/{schedule.id}/approve", json={})
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'approved'

        # confirm
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule/confirm")
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'confirmed'
