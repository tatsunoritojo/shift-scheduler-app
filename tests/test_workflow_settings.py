"""Tests for Phase A': workflow (approval process) settings API."""

import pytest

from app.models.membership import OrganizationMember
from app.models.shift import ShiftSchedule


class TestWorkflowGet:

    def test_new_org_defaults_to_approval_off(self, client, auth, admin_user, db_session):
        """Fresh org with no owner has approval_required=false."""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/settings/workflow')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['approval_required'] is False
        assert data['owner_count'] == 0

    def test_existing_org_with_owner_defaults_on(self, client, auth, admin_user, owner_user, db_session):
        """Org with an owner auto-detects approval_required=true on first access."""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/settings/workflow')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['approval_required'] is True
        assert data['owner_count'] == 1


class TestWorkflowPut:

    def test_turn_on_without_owner_fails(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Initial GET sets approval_required=false (no owner)
        client.get('/api/admin/settings/workflow')
        # Try to turn on without having owner
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': True})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'NO_OWNER'

    def test_turn_on_with_owner_succeeds(self, client, auth, admin_user, owner_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Already true by default (owner exists), but force turning on again
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': True})
        assert resp.status_code == 200
        assert resp.get_json()['approval_required'] is True

    def test_turn_off_blocked_by_pending_schedules(
        self, client, auth, admin_user, owner_user, schedule, db_session,
    ):
        # Set schedule to pending_approval
        schedule.status = 'pending_approval'
        db_session.commit()
        auth.login_as(admin_user)
        # Auto-detect sets approval_required=true because owner exists
        client.get('/api/admin/settings/workflow')
        # Try to turn off
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': False})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['code'] == 'PENDING_APPROVALS_EXIST'
        assert data['pending_schedules_count'] == 1

    def test_turn_off_succeeds_when_no_pending(
        self, client, auth, admin_user, owner_user, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        client.get('/api/admin/settings/workflow')  # auto-init to true
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': False})
        assert resp.status_code == 200
        assert resp.get_json()['approval_required'] is False

    def test_invalid_type_rejected(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': 'yes'})
        assert resp.status_code == 400


class TestWorkflowAuth:

    def test_worker_forbidden(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get('/api/admin/settings/workflow')
        assert resp.status_code == 403

    def test_owner_forbidden(self, client, auth, owner_user, db_session):
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.get('/api/admin/settings/workflow')
        assert resp.status_code == 403
