"""Tests for authentication and role-based access control."""

import pytest


# ---------------------------------------------------------------------------
# Endpoints grouped by required role
# ---------------------------------------------------------------------------

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/opening-hours"),
    ("GET", "/api/admin/periods"),
    ("GET", "/api/admin/workers"),
]

OWNER_ENDPOINTS = [
    ("GET", "/api/owner/pending-approvals"),
]

WORKER_ENDPOINTS = [
    ("GET", "/api/worker/periods"),
]


# ---------------------------------------------------------------------------
# 401 — unauthenticated
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    """Requests without a session must receive 401."""

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS + OWNER_ENDPOINTS + WORKER_ENDPOINTS)
    def test_returns_401(self, client, method, path):
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Authentication required"


# ---------------------------------------------------------------------------
# 403 — wrong role
# ---------------------------------------------------------------------------

class TestForbidden:
    """Authenticated users with wrong role must receive 403."""

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_worker_cannot_access_admin(self, client, auth, worker_user, method, path):
        auth.login_as(worker_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "Insufficient permissions"

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_owner_cannot_access_admin(self, client, auth, owner_user, method, path):
        auth.login_as(owner_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", OWNER_ENDPOINTS)
    def test_worker_cannot_access_owner(self, client, auth, worker_user, method, path):
        auth.login_as(worker_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", WORKER_ENDPOINTS)
    def test_admin_cannot_access_worker(self, client, auth, admin_user, method, path):
        auth.login_as(admin_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 200 — correct role
# ---------------------------------------------------------------------------

class TestAuthorized:
    """Authenticated users with the correct role get 200."""

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_admin_accesses_admin_endpoints(self, client, auth, admin_user, method, path):
        auth.login_as(admin_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 200

    @pytest.mark.parametrize("method,path", OWNER_ENDPOINTS)
    def test_owner_accesses_owner_endpoints(self, client, auth, owner_user, method, path):
        auth.login_as(owner_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 200

    @pytest.mark.parametrize("method,path", WORKER_ENDPOINTS)
    def test_worker_accesses_worker_endpoints(self, client, auth, worker_user, method, path):
        auth.login_as(worker_user)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Inactive user
# ---------------------------------------------------------------------------

class TestInactiveUser:
    """Inactive users must be rejected even with a valid session."""

    def test_inactive_user_gets_401(self, client, auth, admin_user, db_session):
        admin_user.is_active = False
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/periods")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Organization isolation
# ---------------------------------------------------------------------------

class TestOrgIsolation:
    """Users in org A must not see resources belonging to org B."""

    def test_admin_cannot_see_other_org_period(self, client, auth, admin_user, period, db_session):
        from tests.conftest import _make_org, _make_user
        org_b = _make_org(db_session, name="Other Org")
        admin_b = _make_user(db_session, org_b, email="admin_b@test.com", role="admin")
        db_session.commit()

        auth.login_as(admin_b)
        resp = client.get(f"/api/admin/periods/{period.id}/submissions")
        assert resp.status_code == 404
