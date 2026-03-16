"""Tests for worker confirmed-shifts API (GET list + POST manual sync)."""

from datetime import date, datetime
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models.shift import ShiftSchedule, ShiftScheduleEntry
from app.services.auth_service import CredentialsExpiredError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_confirmed_schedule(db_session, period, admin_user):
    s = ShiftSchedule(
        shift_period_id=period.id,
        status="confirmed",
        created_by=admin_user.id,
        confirmed_at=datetime(2026, 3, 15, 12, 0, 0),
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_entry(db_session, schedule, worker_user, shift_date=None, **overrides):
    entry = ShiftScheduleEntry(
        schedule_id=schedule.id,
        user_id=worker_user.id,
        shift_date=shift_date or date(2026, 3, 20),
        start_time="09:00",
        end_time="17:00",
        **overrides,
    )
    db_session.add(entry)
    db_session.flush()
    return entry


# ---------------------------------------------------------------------------
# GET /api/worker/confirmed-shifts
# ---------------------------------------------------------------------------

class TestGetConfirmedShifts:

    def test_returns_own_confirmed_entries(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        auth.login_as(worker_user)

        resp = client.get("/api/worker/confirmed-shifts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["user_id"] == worker_user.id
        assert data[0]["shift_date"] == "2026-03-20"
        # Derived fields
        assert data[0]["is_synced"] is False
        assert data[0]["can_sync"] is True
        assert data[0]["sync_status"] == "pending"

    def test_excludes_other_workers_entries(self, client, auth, worker_user, admin_user, period, org, db_session):
        from app.models.user import User
        from app.models.membership import OrganizationMember
        other = User(google_id="gid_other", email="other@test.com", display_name="Other", role="worker", organization_id=org.id)
        db_session.add(other)
        db_session.flush()
        db_session.add(OrganizationMember(user_id=other.id, organization_id=org.id, role="worker"))
        db_session.flush()

        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, other)  # other worker's entry
        db_session.commit()
        auth.login_as(worker_user)

        resp = client.get("/api/worker/confirmed-shifts")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 0

    def test_sync_status_fields(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        # Synced entry
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 20),
                     calendar_event_id="evt_1", synced_at=datetime(2026, 3, 15))
        # Error entry
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 21),
                     sync_error="CREDENTIALS_EXPIRED")
        # Pending entry
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 22))
        db_session.commit()
        auth.login_as(worker_user)

        resp = client.get("/api/worker/confirmed-shifts")
        data = resp.get_json()
        assert len(data) == 3

        by_date = {d["shift_date"]: d for d in data}
        assert by_date["2026-03-20"]["sync_status"] == "synced"
        assert by_date["2026-03-20"]["can_sync"] is False
        assert by_date["2026-03-21"]["sync_status"] == "reauth_required"
        assert by_date["2026-03-21"]["can_sync"] is True
        assert by_date["2026-03-22"]["sync_status"] == "pending"
        assert by_date["2026-03-22"]["can_sync"] is True


# ---------------------------------------------------------------------------
# POST /api/worker/confirmed-shifts/<id>/sync
# ---------------------------------------------------------------------------

class TestSyncConfirmedShift:

    def test_sync_success(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user, sync_error="NO_CREDENTIALS")
        db_session.commit()
        entry_id = entry.id
        auth.login_as(worker_user)

        fake_creds = object()
        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=fake_creds), \
             patch("app.blueprints.api_worker.create_event", return_value="evt_new_123"):
            resp = client.post(f"/api/worker/confirmed-shifts/{entry_id}/sync")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["calendar_event_id"] == "evt_new_123"
        assert data["is_synced"] is True
        assert data["sync_status"] == "synced"

        # sync_error cleared in DB
        refreshed = db_session.get(ShiftScheduleEntry, entry_id)
        assert refreshed.sync_error is None
        assert refreshed.calendar_event_id == "evt_new_123"

    def test_sync_idempotent_skips_already_synced(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user,
                            calendar_event_id="evt_existing", synced_at=datetime(2026, 3, 15))
        db_session.commit()
        auth.login_as(worker_user)

        mock_create = MagicMock()
        with patch("app.blueprints.api_worker.get_credentials_for_user"), \
             patch("app.blueprints.api_worker.create_event", mock_create):
            resp = client.post(f"/api/worker/confirmed-shifts/{entry.id}/sync")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["skipped"] is True
        assert data["calendar_event_id"] == "evt_existing"
        mock_create.assert_not_called()

    def test_sync_credentials_expired(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        entry_id = entry.id
        auth.login_as(worker_user)

        with patch("app.blueprints.api_worker.get_credentials_for_user",
                    side_effect=CredentialsExpiredError("expired")):
            resp = client.post(f"/api/worker/confirmed-shifts/{entry_id}/sync")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["code"] == "CREDENTIALS_EXPIRED"

        refreshed = db_session.get(ShiftScheduleEntry, entry_id)
        assert refreshed.sync_error == "CREDENTIALS_EXPIRED"

    def test_sync_no_credentials(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        entry_id = entry.id
        auth.login_as(worker_user)

        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=None):
            resp = client.post(f"/api/worker/confirmed-shifts/{entry_id}/sync")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["code"] == "NO_CREDENTIALS"

        refreshed = db_session.get(ShiftScheduleEntry, entry_id)
        assert refreshed.sync_error == "NO_CREDENTIALS"

    def test_sync_rejects_other_workers_entry(self, client, auth, worker_user, admin_user, period, org, db_session):
        from app.models.user import User
        from app.models.membership import OrganizationMember
        other = User(google_id="gid_other2", email="other2@test.com", display_name="Other2", role="worker", organization_id=org.id)
        db_session.add(other)
        db_session.flush()
        db_session.add(OrganizationMember(user_id=other.id, organization_id=org.id, role="worker"))
        db_session.flush()

        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, other)
        db_session.commit()
        auth.login_as(worker_user)

        resp = client.post(f"/api/worker/confirmed-shifts/{entry.id}/sync")
        assert resp.status_code == 404

    def test_sync_calendar_api_error_persisted(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        entry_id = entry.id
        auth.login_as(worker_user)

        fake_creds = object()
        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=fake_creds), \
             patch("app.blueprints.api_worker.create_event", side_effect=Exception("403 Forbidden")):
            resp = client.post(f"/api/worker/confirmed-shifts/{entry_id}/sync")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["code"] == "CALENDAR_PERMISSION_DENIED"

        refreshed = db_session.get(ShiftScheduleEntry, entry_id)
        assert refreshed.sync_error == "CALENDAR_PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# POST /api/worker/confirmed-shifts/sync-all
# ---------------------------------------------------------------------------

class TestSyncAllConfirmedShifts:

    def test_sync_all_success(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 20))
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 21))
        # Already synced — should be excluded
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 22),
                     calendar_event_id="evt_existing", synced_at=datetime(2026, 3, 15))
        db_session.commit()
        auth.login_as(worker_user)

        call_count = 0
        def fake_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"evt_bulk_{call_count}"

        fake_creds = object()
        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=fake_creds), \
             patch("app.blueprints.api_worker.create_event", side_effect=fake_create):
            resp = client.post("/api/worker/confirmed-shifts/sync-all")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["synced"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2

    def test_sync_all_no_unsynced(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user, calendar_event_id="evt_1", synced_at=datetime(2026, 3, 15))
        db_session.commit()
        auth.login_as(worker_user)

        resp = client.post("/api/worker/confirmed-shifts/sync-all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["synced"] == 0
        assert data["results"] == []

    def test_sync_all_credentials_expired(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        auth.login_as(worker_user)

        with patch("app.blueprints.api_worker.get_credentials_for_user",
                    side_effect=CredentialsExpiredError("expired")):
            resp = client.post("/api/worker/confirmed-shifts/sync-all")

        assert resp.status_code == 401
        assert resp.get_json()["code"] == "CREDENTIALS_EXPIRED"

    def test_sync_all_partial_failure(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 20))
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 21))
        db_session.commit()
        auth.login_as(worker_user)

        call_count = 0
        def fake_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("403 Forbidden")
            return f"evt_bulk_{call_count}"

        fake_creds = object()
        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=fake_creds), \
             patch("app.blueprints.api_worker.create_event", side_effect=fake_create):
            resp = client.post("/api/worker/confirmed-shifts/sync-all")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["synced"] == 1
        assert data["failed"] == 1

    def test_sync_all_sets_last_sync_attempt_at(self, client, auth, worker_user, admin_user, period, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        entry = _make_entry(db_session, schedule, worker_user)
        db_session.commit()
        entry_id = entry.id
        auth.login_as(worker_user)

        fake_creds = object()
        with patch("app.blueprints.api_worker.get_credentials_for_user", return_value=fake_creds), \
             patch("app.blueprints.api_worker.create_event", return_value="evt_1"):
            client.post("/api/worker/confirmed-shifts/sync-all")

        refreshed = db_session.get(ShiftScheduleEntry, entry_id)
        assert refreshed.last_sync_attempt_at is not None


# ---------------------------------------------------------------------------
# GET /api/admin/schedules/<id> — sync_summary
# ---------------------------------------------------------------------------

class TestAdminSyncSummary:

    def test_sync_summary_in_confirmed_schedule(self, client, auth, admin_user, period, worker_user, db_session):
        schedule = _make_confirmed_schedule(db_session, period, admin_user)
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 20),
                     calendar_event_id="evt_1", synced_at=datetime(2026, 3, 15))
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 21))
        _make_entry(db_session, schedule, worker_user, shift_date=date(2026, 3, 22),
                     sync_error="CREDENTIALS_EXPIRED")
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.get(f"/api/admin/periods/{period.id}/schedule")
        assert resp.status_code == 200
        data = resp.get_json()
        summary = data.get("sync_summary")
        assert summary is not None
        assert summary["total"] == 3
        assert summary["synced"] == 1
        assert summary["pending"] == 1
        assert summary["reauth_required"] == 1

    def test_no_sync_summary_for_draft(self, client, auth, admin_user, period, worker_user, db_session):
        s = ShiftSchedule(shift_period_id=period.id, status="draft", created_by=admin_user.id)
        db_session.add(s)
        db_session.flush()
        _make_entry(db_session, s, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.get(f"/api/admin/periods/{period.id}/schedule")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sync_summary" not in data
