"""Tests for invite code, landing page, cookie token passing, invitation email, and token entropy."""

import re
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.organization import Organization
from app.models.membership import OrganizationMember, InvitationToken


# ---------------------------------------------------------------------------
# Invite Code CRUD
# ---------------------------------------------------------------------------

class TestInviteCode:

    def test_get_invite_code_initially_null(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/invite-code")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["invite_code"] is None
        assert data["invite_code_enabled"] is False

    def test_generate_invite_code(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/invite-code")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["invite_code"] is not None
        assert len(data["invite_code"]) >= 16
        assert data["invite_code_enabled"] is True

    def test_regenerate_invite_code(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp1 = client.post("/api/admin/invite-code")
        code1 = resp1.get_json()["invite_code"]
        resp2 = client.post("/api/admin/invite-code")
        code2 = resp2.get_json()["invite_code"]
        assert code1 != code2

    def test_toggle_invite_code(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post("/api/admin/invite-code")
        # Disable
        resp = client.put("/api/admin/invite-code", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.get_json()["invite_code_enabled"] is False
        # Re-enable
        resp = client.put("/api/admin/invite-code", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.get_json()["invite_code_enabled"] is True

    def test_toggle_rejects_non_boolean(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put("/api/admin/invite-code", json={"enabled": "yes"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Invite Landing Page
# ---------------------------------------------------------------------------

class TestInviteLandingPage:

    def test_invite_page_served(self, client, db_session):
        db_session.commit()
        resp = client.get("/invite")
        assert resp.status_code == 200
        assert b"invite" in resp.data.lower()

    def test_invite_info_with_valid_code(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = True
        db_session.commit()

        resp = client.get(f"/api/invite/info?code={org.invite_code}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["organization_name"] == org.name
        assert data["role"] == "worker"
        assert "/auth/invite/code/" in data["login_url"]

    def test_invite_info_with_disabled_code(self, client, org, db_session):
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = False
        db_session.commit()

        resp = client.get(f"/api/invite/info?code={org.invite_code}")
        assert resp.status_code == 404

    def test_invite_info_with_valid_token(self, client, admin_user, org, db_session):
        token = InvitationToken(
            organization_id=org.id,
            role="owner",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/api/invite/info?token={token.token}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["organization_name"] == org.name
        assert data["role"] == "owner"

    def test_invite_info_with_expired_token(self, client, admin_user, org, db_session):
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/api/invite/info?token={token.token}")
        assert resp.status_code == 404

    def test_invite_info_no_params(self, client, db_session):
        db_session.commit()
        resp = client.get("/api/invite/info")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cookie Token Passing
# ---------------------------------------------------------------------------

class TestCookieTokenPassing:

    def test_accept_invite_sets_cookie(self, client, admin_user, org, db_session):
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.commit()

        resp = client.get(f"/auth/invite/{token.token}")
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/auth/google/login" in location
        assert f"invite_token={token.token}" in location
        # Check that cookie is set in response
        cookie_header = resp.headers.get_all("Set-Cookie")
        cookie_names = [c.split("=")[0] for c in cookie_header]
        assert "invite_token" in cookie_names

    def test_accept_invite_code_sets_cookie(self, client, org, db_session):
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = True
        db_session.commit()

        resp = client.get(f"/auth/invite/code/{org.invite_code}")
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["Location"]
        cookie_header = resp.headers.get_all("Set-Cookie")
        cookie_names = [c.split("=")[0] for c in cookie_header]
        assert "invite_code" in cookie_names

    def test_reject_invalid_invite_code(self, client, db_session):
        db_session.commit()
        resp = client.get("/auth/invite/code/nonexistent")
        assert resp.status_code == 400

    def test_accept_invite_code_passes_query_param(self, client, org, db_session):
        """Invite code redirect should pass code as query param to login."""
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = True
        db_session.commit()

        resp = client.get(f"/auth/invite/code/{org.invite_code}")
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert f"invite_code={org.invite_code}" in location

    def test_login_stores_invite_code_in_session(self, client, org, db_session):
        """login() should store invite_code from query param into session."""
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = True
        db_session.commit()

        # Call login with invite_code query param (simulates redirect from accept_invite_code)
        client.get(f"/auth/google/login?invite_code={org.invite_code}")

        with client.session_transaction() as sess:
            assert sess.get('invite_code') == org.invite_code
            assert 'state' in sess  # OAuth state stored in same request

    def test_resolve_invite_code_session_fallback(self, client, org, db_session):
        """When cookie is lost (mobile), invite code should resolve from session."""
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_enabled = True
        db_session.commit()

        from app.blueprints.auth import _resolve_invite_code
        with client.application.test_request_context():
            from flask import session as flask_session
            flask_session['invite_code'] = org.invite_code
            result = _resolve_invite_code()
            assert result is not None
            assert result.id == org.id


# ---------------------------------------------------------------------------
# Invitation Email
# ---------------------------------------------------------------------------

class TestInvitationEmail:

    def test_email_sent_when_email_specified(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        with patch("app.services.notification_service.notify_invitation_created") as mock_notify:
            resp = client.post("/api/admin/invitations", json={
                "role": "worker",
                "email": "newworker@test.com",
                "expires_hours": 48,
            })
            assert resp.status_code == 201
            mock_notify.assert_called_once()

    def test_no_email_when_email_not_specified(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        with patch("app.services.notification_service.notify_invitation_created") as mock_notify:
            resp = client.post("/api/admin/invitations", json={
                "role": "worker",
                "expires_hours": 48,
            })
            assert resp.status_code == 201
            mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Token Entropy
# ---------------------------------------------------------------------------

class TestTokenEntropy:

    def test_invitation_token_is_url_safe(self, db_session, admin_user, org):
        """Token should only contain URL-safe characters (alphanumeric, -, _)."""
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.flush()
        assert re.match(r'^[A-Za-z0-9_-]+$', token.token), f"Token contains non-URL-safe chars: {token.token}"

    def test_invitation_token_length(self, db_session, admin_user, org):
        """secrets.token_urlsafe(32) produces a 43-character string."""
        token = InvitationToken(
            organization_id=org.id,
            role="worker",
            created_by=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        db_session.flush()
        assert len(token.token) == 43
