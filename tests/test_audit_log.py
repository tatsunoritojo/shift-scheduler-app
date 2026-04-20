"""Tests for audit logging and OAuth credential error handling."""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.shift import ShiftSchedule


# ---------------------------------------------------------------------------
# AuditLog model basics
# ---------------------------------------------------------------------------

class TestAuditLogModel:

    def test_create_audit_entry(self, app, db_session, admin_user, org):
        db_session.commit()
        with app.app_context():
            entry = AuditLog(
                organization_id=org.id,
                actor_id=admin_user.id,
                action='ROLE_CHANGED',
                resource_type='OrganizationMember',
                resource_id=1,
                old_values={'role': 'worker'},
                new_values={'role': 'owner'},
                status='SUCCESS',
            )
            db_session.add(entry)
            db_session.commit()
            assert entry.id is not None
            d = entry.to_dict()
            assert d['action'] == 'ROLE_CHANGED'
            assert d['old_values'] == {'role': 'worker'}
            assert d['new_values'] == {'role': 'owner'}
            assert d['actor_email'] == admin_user.email


# ---------------------------------------------------------------------------
# Audit logs recorded on RBAC operations
# ---------------------------------------------------------------------------

class TestAuditOnRoleChange:

    def test_role_change_creates_audit_entry(self, client, auth, admin_user, worker_user, org, db_session):
        from app.models.membership import OrganizationMember
        db_session.commit()

        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={"role": "owner"})
        assert resp.status_code == 200

        logs = AuditLog.query.filter_by(
            action='ROLE_CHANGED',
            resource_type='OrganizationMember',
            resource_id=member.id,
        ).all()
        assert len(logs) == 1
        assert logs[0].old_values == {'role': 'worker'}
        assert logs[0].new_values == {'role': 'owner'}
        assert logs[0].actor_id == admin_user.id
        assert logs[0].organization_id == org.id


class TestAuditOnMemberRemoval:

    def test_member_removal_creates_audit_entry(self, client, auth, admin_user, worker_user, org, db_session):
        from app.models.membership import OrganizationMember
        db_session.commit()

        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/members/{member.id}")
        assert resp.status_code == 204

        logs = AuditLog.query.filter_by(
            action='MEMBER_REMOVED',
            resource_type='OrganizationMember',
        ).all()
        assert len(logs) == 1
        assert logs[0].old_values['role'] == 'worker'
        assert logs[0].actor_id == admin_user.id


class TestAuditOnInvitations:

    def test_invitation_create_creates_audit_entry(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invitations", json={"role": "worker"})
        assert resp.status_code == 201

        logs = AuditLog.query.filter_by(action='INVITATION_CREATED').all()
        assert len(logs) == 1
        assert logs[0].new_values['role'] == 'worker'

    def test_invitation_revoke_creates_audit_entry(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        create_resp = client.post("/api/admin/invitations", json={"role": "owner"})
        token_id = create_resp.get_json()["id"]

        resp = client.delete(f"/api/admin/invitations/{token_id}")
        assert resp.status_code == 204

        logs = AuditLog.query.filter_by(action='INVITATION_REVOKED').all()
        assert len(logs) == 1
        assert logs[0].resource_id == token_id


class TestAuditOnApproval:

    def test_submit_for_approval_creates_audit_entry(
        self, client, auth, admin_user, owner_user, schedule, period, org, db_session
    ):
        # owner_user fixture triggers approval_required=true auto-detection
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule/submit")
        assert resp.status_code == 200

        logs = AuditLog.query.filter_by(action='SCHEDULE_SUBMITTED').all()
        assert len(logs) == 1
        assert logs[0].resource_id == schedule.id


# ---------------------------------------------------------------------------
# Dashboard audit-logs endpoint
# ---------------------------------------------------------------------------

class TestAuditLogAPI:

    def test_list_audit_logs(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        # Create some audit entries
        for action in ['ROLE_CHANGED', 'MEMBER_REMOVED', 'INVITATION_CREATED']:
            db_session.add(AuditLog(
                organization_id=org.id,
                actor_id=admin_user.id,
                action=action,
                resource_type='Test',
            ))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get("/api/admin/dashboard/audit-logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3

    def test_filter_by_action(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        for action in ['ROLE_CHANGED', 'MEMBER_REMOVED']:
            db_session.add(AuditLog(
                organization_id=org.id,
                actor_id=admin_user.id,
                action=action,
                resource_type='Test',
            ))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get("/api/admin/dashboard/audit-logs?action=ROLE_CHANGED")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['action'] == 'ROLE_CHANGED'

    def test_org_isolation(self, client, auth, admin_user, org, db_session):
        """Audit logs from other orgs are not visible."""
        from tests.conftest import _make_org, _make_user
        org_b = _make_org(db_session, name="Other Org")
        db_session.add(AuditLog(
            organization_id=org_b.id,
            action='ROLE_CHANGED',
            resource_type='Test',
        ))
        db_session.add(AuditLog(
            organization_id=org.id,
            actor_id=admin_user.id,
            action='MEMBER_REMOVED',
            resource_type='Test',
        ))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get("/api/admin/dashboard/audit-logs")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['organization_id'] == org.id


# ---------------------------------------------------------------------------
# CredentialsExpiredError handling
# ---------------------------------------------------------------------------

class TestCredentialsExpiredError:

    def test_calendar_returns_401_on_credentials_expired(self, client, auth, worker_user, db_session):
        from app.services.auth_service import CredentialsExpiredError
        db_session.commit()
        auth.login_as(worker_user)

        with patch(
            'app.blueprints.api_calendar.get_credentials_for_user',
            side_effect=CredentialsExpiredError("Token expired"),
        ):
            resp = client.get("/api/calendar/events?startDate=2026-03-01&endDate=2026-03-31")
            assert resp.status_code == 401
            data = resp.get_json()
            assert data['code'] == 'CREDENTIALS_EXPIRED'

    def test_worker_calendars_returns_401_on_credentials_expired(self, client, auth, worker_user, db_session):
        from app.services.auth_service import CredentialsExpiredError
        db_session.commit()
        auth.login_as(worker_user)

        with patch(
            'app.blueprints.api_worker.get_credentials_for_user',
            side_effect=CredentialsExpiredError("Token expired"),
        ):
            resp = client.get("/api/worker/calendars")
            assert resp.status_code == 401
            assert resp.get_json()['code'] == 'CREDENTIALS_EXPIRED'
