"""Tests for RBAC: member management, invitations, role changes."""

from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models.membership import OrganizationMember, InvitationToken


# ---------------------------------------------------------------------------
# Member listing
# ---------------------------------------------------------------------------

class TestMemberList:

    def test_list_members(self, client, auth, admin_user, owner_user, worker_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/members")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3  # admin, owner, worker
        emails = {m["user_email"] for m in data}
        assert "admin@test.com" in emails
        assert "worker@test.com" in emails


# ---------------------------------------------------------------------------
# Role changes
# ---------------------------------------------------------------------------

class TestRoleChange:

    def test_change_worker_to_owner(self, client, auth, admin_user, worker_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={"role": "owner"})
        assert resp.status_code == 200
        assert resp.get_json()["role"] == "owner"
        # Verify User model is synced
        db_session.refresh(worker_user)
        assert worker_user.role == "owner"

    def test_reject_invalid_role(self, client, auth, admin_user, worker_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={"role": "superadmin"})
        assert resp.status_code == 400

    def test_cannot_remove_last_admin(self, client, auth, admin_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={"role": "worker"})
        assert resp.status_code == 400
        assert "last admin" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Member removal
# ---------------------------------------------------------------------------

class TestMemberRemoval:

    def test_remove_worker(self, client, auth, admin_user, worker_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/members/{member.id}")
        assert resp.status_code == 204
        db_session.refresh(member)
        assert member.is_active is False
        # User account remains active (only membership is deactivated)
        db_session.refresh(worker_user)
        assert worker_user.is_active is True

    def test_cannot_remove_self(self, client, auth, admin_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/members/{member.id}")
        assert resp.status_code == 400
        assert "yourself" in resp.get_json()["error"]

    def test_cannot_remove_last_admin(self, client, auth, admin_user, db_session):
        db_session.commit()
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/members/{member.id}")
        # Blocked both by self-removal and last-admin check
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Invitation CRUD
# ---------------------------------------------------------------------------

class TestInvitations:

    def test_create_invitation(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invitations", json={
            "role": "worker",
            "expires_hours": 48,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["role"] == "worker"
        assert data["is_valid"] is True
        assert len(data["token"]) >= 32  # secrets.token_urlsafe(32)

    def test_create_email_restricted_invitation(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invitations", json={
            "role": "owner",
            "email": "newowner@test.com",
        })
        assert resp.status_code == 201
        assert resp.get_json()["email"] == "newowner@test.com"

    def test_reject_invalid_role_in_invitation(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invitations", json={"role": "superadmin"})
        assert resp.status_code == 400

    def test_reject_invalid_expiry(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invitations", json={
            "role": "worker",
            "expires_hours": 0,
        })
        assert resp.status_code == 400

    def test_list_invitations(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Create two tokens
        client.post("/api/admin/invitations", json={"role": "worker"})
        client.post("/api/admin/invitations", json={"role": "owner"})
        resp = client.get("/api/admin/invitations")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_revoke_invitation(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        create_resp = client.post("/api/admin/invitations", json={"role": "worker"})
        token_id = create_resp.get_json()["id"]
        resp = client.delete(f"/api/admin/invitations/{token_id}")
        assert resp.status_code == 204
        # Token should now be expired
        token = db_session.get(InvitationToken, token_id)
        assert not token.is_valid


# ---------------------------------------------------------------------------
# Invitation acceptance (auth flow)
# ---------------------------------------------------------------------------

class TestInvitationAcceptance:

    def test_accept_invite_endpoint_stores_token_in_session(self, client, auth, admin_user, org, db_session):
        """GET /auth/invite/<token> stores the token and redirects to login."""
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/auth/invite/{token.token}")
        assert resp.status_code == 302  # redirect to login
        assert "/auth/google/login" in resp.headers["Location"]

    def test_reject_invalid_token(self, client, db_session):
        db_session.commit()
        resp = client.get("/auth/invite/nonexistent_token")
        assert resp.status_code == 400

    def test_reject_expired_token(self, client, auth, admin_user, org, db_session):
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # expired
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/auth/invite/{token.token}")
        assert resp.status_code == 400

    def test_reject_used_token(self, client, auth, admin_user, worker_user, org, db_session):
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
            used_at=datetime.utcnow(),
            used_by=worker_user.id,
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/auth/invite/{token.token}")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Organization isolation for members
# ---------------------------------------------------------------------------

class TestMemberOrgIsolation:

    def test_admin_cannot_see_other_org_members(self, client, auth, admin_user, db_session):
        from tests.conftest import _make_org, _make_user
        org_b = _make_org(db_session, name="Other Org")
        admin_b = _make_user(db_session, org_b, email="admin_b@test.com", role="admin")
        db_session.commit()

        auth.login_as(admin_b)
        resp = client.get("/api/admin/members")
        data = resp.get_json()
        # Should only see members of org_b
        assert all(m["organization_id"] == org_b.id for m in data)

    def test_admin_cannot_modify_other_org_member(self, client, auth, worker_user, db_session):
        from tests.conftest import _make_org, _make_user
        org_b = _make_org(db_session, name="Other Org")
        admin_b = _make_user(db_session, org_b, email="admin_b2@test.com", role="admin")
        db_session.commit()

        member = OrganizationMember.query.filter_by(user_id=worker_user.id).first()
        auth.login_as(admin_b)
        resp = client.put(f"/api/admin/members/{member.id}/role", json={"role": "owner"})
        assert resp.status_code == 404
