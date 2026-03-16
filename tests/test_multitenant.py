"""Tests for multi-tenant enforcement: org membership gates, upsert isolation, CORS."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMember, InvitationToken


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orgless_user(session):
    """Create a user with no organization membership."""
    user = User(
        google_id="gid_orgless",
        email="orgless@example.com",
        display_name="No Org",
        role="worker",
        organization_id=None,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Middleware: require_role blocks users without org membership
# ---------------------------------------------------------------------------

class TestOrgMembershipGate:

    def test_require_role_blocks_orgless_user(self, client, auth, db_session):
        """User without OrganizationMember is rejected by require_role."""
        user = _make_orgless_user(db_session)
        db_session.commit()

        auth.login_as(user)
        resp = client.get("/api/worker/periods")
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["code"] == "ORG_MEMBERSHIP_REQUIRED"

    def test_require_auth_blocks_orgless_user(self, client, auth, db_session):
        """User without OrganizationMember is rejected by require_auth (calendar)."""
        user = _make_orgless_user(db_session)
        db_session.commit()

        auth.login_as(user)
        resp = client.get("/api/calendar/events?startDate=2026-03-01&endDate=2026-03-31")
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["code"] == "ORG_MEMBERSHIP_REQUIRED"

    def test_require_role_allows_user_with_membership(
        self, client, auth, admin_user, db_session
    ):
        """User with active OrganizationMember passes require_role."""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/members")
        assert resp.status_code == 200

    def test_inactive_membership_is_blocked(self, client, auth, db_session, org):
        """User whose membership is deactivated is blocked."""
        user = User(
            google_id="gid_deactivated",
            email="deact@test.com",
            display_name="Deactivated",
            role="worker",
            organization_id=org.id,
        )
        db_session.add(user)
        db_session.flush()
        membership = OrganizationMember(
            user_id=user.id,
            organization_id=org.id,
            role="worker",
            is_active=False,
        )
        db_session.add(membership)
        db_session.commit()

        auth.login_as(user)
        resp = client.get("/api/worker/periods")
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "ORG_MEMBERSHIP_REQUIRED"


# ---------------------------------------------------------------------------
# upsert_user: non-invited users don't get auto-assigned to first org
# ---------------------------------------------------------------------------

class TestUpsertUserIsolation:

    def test_non_invited_user_gets_no_org(self, app, db_session, org):
        """User not matching env emails and without invitation stays org-less."""
        db_session.commit()
        with app.app_context():
            from app.services.auth_service import upsert_user
            user = upsert_user("gid_random", "random@example.com", "Random")
            assert user.organization_id is None
            membership = OrganizationMember.query.filter_by(user_id=user.id).first()
            assert membership is None

    def test_env_admin_email_gets_auto_assigned(self, app, db_session, org):
        """User matching ADMIN_EMAIL env var gets auto-assigned to first org."""
        db_session.commit()
        with app.app_context():
            app.config['ADMIN_EMAIL'] = 'env_admin@test.com'
            from app.services.auth_service import upsert_user
            user = upsert_user("gid_envadmin", "env_admin@test.com", "Env Admin")
            assert user.organization_id == org.id
            membership = OrganizationMember.query.filter_by(user_id=user.id).first()
            assert membership is not None
            assert membership.role == "admin"

    def test_invited_user_gets_correct_org(self, app, db_session, org, admin_user):
        """User with invitation token is assigned to the token's org."""
        token = InvitationToken(
            organization_id=org.id,
            role="owner",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.commit()

        with app.app_context():
            from app.services.auth_service import upsert_user
            user = upsert_user("gid_invited", "invited@test.com", "Invited", invitation_token=token)
            assert user.organization_id == org.id
            assert user.role == "owner"
            membership = OrganizationMember.query.filter_by(user_id=user.id).first()
            assert membership is not None
            assert membership.role == "owner"


# ---------------------------------------------------------------------------
# Page routes: org-less users redirect to /no-organization
# ---------------------------------------------------------------------------

class TestNoOrgRedirects:

    def test_index_redirects_orgless_to_no_org(self, client, auth, db_session):
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/no-organization" in resp.headers["Location"]

    def test_worker_page_redirects_orgless(self, client, auth, db_session):
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)
        resp = client.get("/worker")
        assert resp.status_code == 302
        assert "/no-organization" in resp.headers["Location"]

    def test_admin_page_redirects_orgless(self, client, auth, db_session):
        user = _make_orgless_user(db_session)
        user.role = "admin"
        db_session.commit()
        auth.login_as(user)
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert "/no-organization" in resp.headers["Location"]

    def test_no_org_page_redirects_if_has_org(self, client, auth, worker_user, db_session):
        """User with org visiting /no-organization is redirected to /."""
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get("/no-organization")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

    def test_no_org_page_accessible_when_orgless(self, client, auth, db_session):
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)
        resp = client.get("/no-organization")
        assert resp.status_code == 200
        assert "シフリーへようこそ" in resp.data.decode("utf-8")


# ---------------------------------------------------------------------------
# /auth/me includes organization_id
# ---------------------------------------------------------------------------

class TestAuthMeOrgField:

    def test_me_includes_organization_id(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get("/auth/me")
        data = resp.get_json()
        assert "organization_id" in data
        assert data["organization_id"] == worker_user.organization_id

    def test_me_shows_null_org_for_orgless_user(self, client, auth, db_session):
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)
        resp = client.get("/auth/me")
        data = resp.get_json()
        assert data["organization_id"] is None


# ---------------------------------------------------------------------------
# POST /api/organizations: org-less user can create a new organization
# ---------------------------------------------------------------------------

class TestCreateOrganization:

    def test_create_org_success(self, client, auth, db_session):
        """Org-less user can create a new organization and become admin."""
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)

        resp = client.post("/api/organizations", json={"name": "My Shop"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "My Shop"
        assert data["role"] == "admin"
        assert "id" in data

        # Verify user is now admin of the new org
        db_session.expire_all()
        assert user.role == "admin"
        assert user.organization_id == data["id"]

        # Verify OrganizationMember record exists
        member = OrganizationMember.query.filter_by(
            user_id=user.id, organization_id=data["id"]
        ).first()
        assert member is not None
        assert member.role == "admin"
        assert member.is_active is True

    def test_create_org_default_name(self, client, auth, db_session):
        """If no name is provided, a default name is generated."""
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)

        resp = client.post("/api/organizations", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert user.display_name in data["name"]

    def test_create_org_rejects_if_already_member(self, client, auth, admin_user, db_session):
        """User who already belongs to an org cannot create another."""
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/organizations", json={"name": "Dup"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "ALREADY_MEMBER"

    def test_create_org_requires_auth(self, client):
        """Unauthenticated request is rejected."""
        resp = client.post("/api/organizations", json={"name": "No Auth"})
        assert resp.status_code == 401

    def test_create_org_name_too_long(self, client, auth, db_session):
        """Organization name exceeding 255 chars is rejected."""
        user = _make_orgless_user(db_session)
        db_session.commit()
        auth.login_as(user)

        resp = client.post("/api/organizations", json={"name": "x" * 256})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"
