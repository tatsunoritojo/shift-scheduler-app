"""Tests for linked calendar accounts (secondary Google account for read-only calendar access)."""

from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models.user import LinkedCalendarAccount
from app.utils.crypto import encrypt_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_linked_account(db_session, user, google_sub='linked_sub_1',
                           google_email='personal@gmail.com', is_active=True):
    linked = LinkedCalendarAccount(
        user_id=user.id,
        google_sub=google_sub,
        google_email=google_email,
        refresh_token=encrypt_token('fake_refresh_token'),
        scopes='openid,calendar.readonly',
        is_active=is_active,
    )
    db_session.add(linked)
    db_session.commit()
    return linked


# ---------------------------------------------------------------------------
# GET /api/worker/calendar-links
# ---------------------------------------------------------------------------

class TestGetCalendarLinks:

    def test_returns_active_links(self, client, auth, worker_user, db_session):
        _create_linked_account(db_session, worker_user)
        _create_linked_account(db_session, worker_user,
                               google_sub='linked_sub_2', google_email='uni@gmail.com')
        auth.login_as(worker_user)

        resp = client.get('/api/worker/calendar-links')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        emails = {d['google_email'] for d in data}
        assert 'personal@gmail.com' in emails
        assert 'uni@gmail.com' in emails

    def test_excludes_inactive_links(self, client, auth, worker_user, db_session):
        _create_linked_account(db_session, worker_user, is_active=False)
        auth.login_as(worker_user)

        resp = client.get('/api/worker/calendar-links')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 0

    def test_excludes_other_users_links(self, client, auth, worker_user, admin_user, db_session):
        _create_linked_account(db_session, admin_user)
        auth.login_as(worker_user)

        resp = client.get('/api/worker/calendar-links')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 0


# ---------------------------------------------------------------------------
# DELETE /api/worker/calendar-links/<id>
# ---------------------------------------------------------------------------

class TestDeleteCalendarLink:

    def test_delete_own_link(self, client, auth, worker_user, db_session):
        linked = _create_linked_account(db_session, worker_user)
        auth.login_as(worker_user)

        resp = client.delete(f'/api/worker/calendar-links/{linked.id}')
        assert resp.status_code == 200

        # Verify deleted
        assert db_session.get(LinkedCalendarAccount, linked.id) is None

    def test_cannot_delete_others_link(self, client, auth, worker_user, admin_user, db_session):
        linked = _create_linked_account(db_session, admin_user)
        auth.login_as(worker_user)

        resp = client.delete(f'/api/worker/calendar-links/{linked.id}')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/worker/calendars — integration with linked accounts
# ---------------------------------------------------------------------------

class TestCalendarsIntegration:

    def test_calendars_include_linked_accounts(self, client, auth, worker_user, db_session):
        linked = _create_linked_account(db_session, worker_user)
        auth.login_as(worker_user)

        primary_cals = [{'id': 'primary', 'summary': 'Work', 'accessRole': 'owner', 'primary': True}]
        linked_cals = [{'id': 'personal_cal', 'summary': 'Personal', 'accessRole': 'owner'}]

        call_count = [0]
        def mock_list_calendars(creds):
            call_count[0] += 1
            return primary_cals if call_count[0] == 1 else linked_cals

        fake_creds = MagicMock()

        with patch('app.blueprints.api_worker.get_credentials_for_user', return_value=fake_creds), \
             patch('app.blueprints.api_worker.get_credentials_for_linked_account', return_value=fake_creds), \
             patch('app.blueprints.api_worker.list_calendars', side_effect=mock_list_calendars):
            resp = client.get('/api/worker/calendars')

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

        primary = [c for c in data if c['source_type'] == 'primary']
        linked_items = [c for c in data if c['source_type'] == 'linked']
        assert len(primary) == 1
        assert len(linked_items) == 1
        assert linked_items[0]['account_email'] == 'personal@gmail.com'

    def test_calendars_graceful_on_linked_failure(self, client, auth, worker_user, db_session):
        _create_linked_account(db_session, worker_user)
        auth.login_as(worker_user)

        primary_cals = [{'id': 'primary', 'summary': 'Work', 'accessRole': 'owner'}]
        fake_creds = MagicMock()

        with patch('app.blueprints.api_worker.get_credentials_for_user', return_value=fake_creds), \
             patch('app.blueprints.api_worker.get_credentials_for_linked_account', side_effect=Exception('token error')), \
             patch('app.blueprints.api_worker.list_calendars', return_value=primary_cals):
            resp = client.get('/api/worker/calendars')

        assert resp.status_code == 200
        data = resp.get_json()
        # Only primary calendars returned, linked failure is graceful
        assert len(data) == 1
        assert data[0]['source_type'] == 'primary'


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class TestLinkedCalendarAccountModel:

    def test_unique_constraint(self, client, auth, worker_user, db_session):
        _create_linked_account(db_session, worker_user)
        with pytest.raises(Exception):
            _create_linked_account(db_session, worker_user)  # same google_sub

    def test_to_dict(self, client, auth, worker_user, db_session):
        linked = _create_linked_account(db_session, worker_user)
        d = linked.to_dict()
        assert d['google_email'] == 'personal@gmail.com'
        assert 'refresh_token' not in d  # Should not expose token
