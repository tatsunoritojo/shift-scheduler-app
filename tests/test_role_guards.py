"""Tests for Phase A': role change guards (self-role, last owner, impact API)."""

import pytest

from app.extensions import db
from app.models.membership import OrganizationMember


class TestSelfRoleChangeGuard:

    def test_cannot_change_own_role(self, client, auth, admin_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={'role': 'worker'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'SELF_ROLE_CHANGE'

    def test_can_change_other_member_role(
        self, client, auth, admin_user, worker_user, db_session,
    ):
        db_session.commit()
        target = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{target.id}/role", json={'role': 'admin'})
        assert resp.status_code == 200


class TestLastOwnerGuard:

    def test_last_owner_cannot_be_demoted_when_approval_on(
        self, client, auth, admin_user, owner_user, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        # Auto-detect sets approval_required=true
        client.get('/api/admin/settings/workflow')

        owner_member = OrganizationMember.query.filter_by(user_id=owner_user.id).first()
        resp = client.put(f"/api/admin/members/{owner_member.id}/role", json={'role': 'worker'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'LAST_OWNER'

    def test_last_owner_cannot_be_removed_when_approval_on(
        self, client, auth, admin_user, owner_user, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        client.get('/api/admin/settings/workflow')

        owner_member = OrganizationMember.query.filter_by(user_id=owner_user.id).first()
        resp = client.delete(f"/api/admin/members/{owner_member.id}")
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'LAST_OWNER'

    def test_owner_can_be_demoted_when_approval_off(
        self, client, auth, admin_user, owner_user, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        # Turn approval OFF (owner exists so default is ON, then explicitly disable)
        client.get('/api/admin/settings/workflow')
        resp = client.put('/api/admin/settings/workflow', json={'approval_required': False})
        assert resp.status_code == 200

        owner_member = OrganizationMember.query.filter_by(user_id=owner_user.id).first()
        resp = client.put(f"/api/admin/members/{owner_member.id}/role", json={'role': 'worker'})
        assert resp.status_code == 200


class TestRoleChangeImpactAPI:

    def test_impact_detects_self(self, client, auth, admin_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        auth.login_as(admin_user)
        resp = client.get(f"/api/admin/members/{member.id}/role-change-impact?new_role=worker")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_self'] is True

    def test_impact_detects_last_owner(
        self, client, auth, admin_user, owner_user, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        client.get('/api/admin/settings/workflow')  # auto-enable approval
        owner_member = OrganizationMember.query.filter_by(user_id=owner_user.id).first()
        resp = client.get(f"/api/admin/members/{owner_member.id}/role-change-impact?new_role=worker")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_last_owner_while_approval_required'] is True

    def test_impact_detects_pending(
        self, client, auth, admin_user, owner_user, schedule, db_session,
    ):
        schedule.status = 'pending_approval'
        db_session.commit()
        auth.login_as(admin_user)
        client.get('/api/admin/settings/workflow')
        owner_member = OrganizationMember.query.filter_by(user_id=owner_user.id).first()
        resp = client.get(f"/api/admin/members/{owner_member.id}/role-change-impact?new_role=worker")
        data = resp.get_json()
        assert data['pending_schedules_count'] == 1
        assert data['requires_confirmation'] is True


class TestOptimisticLock:

    def test_save_accepts_matching_version(
        self, client, auth, admin_user, period, schedule, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        # GET current version
        resp = client.get(f"/api/admin/periods/{period.id}/schedule")
        assert resp.status_code == 200
        version = resp.get_json().get('schedule_version')
        assert version is not None
        # POST with matching version should succeed
        resp = client.post(
            f"/api/admin/periods/{period.id}/schedule",
            json={'entries': [], 'expected_version': version},
        )
        assert resp.status_code == 200

    def test_save_rejects_stale_version(
        self, client, auth, admin_user, period, schedule, db_session,
    ):
        db_session.commit()
        auth.login_as(admin_user)
        # Stale version
        resp = client.post(
            f"/api/admin/periods/{period.id}/schedule",
            json={'entries': [], 'expected_version': '1970-01-01T00:00:00'},
        )
        assert resp.status_code == 409
        assert resp.get_json()['code'] == 'SCHEDULE_VERSION_MISMATCH'

    def test_save_without_version_still_works(
        self, client, auth, admin_user, period, schedule, db_session,
    ):
        """Backwards compat: old clients without expected_version still succeed."""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/schedule", json={'entries': []})
        assert resp.status_code == 200
