"""Tests for reminder notifications — settings CRUD, auto-send, manual send, dedup, stats."""

from datetime import datetime, date, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.organization import Organization
from app.models.shift import ShiftPeriod, ShiftSubmission, ShiftSchedule, ShiftScheduleEntry
from app.models.reminder import Reminder
from app.models.user import User
from tests.conftest import _make_org, _make_user


# ---------------------------------------------------------------------------
# Reminder Settings CRUD
# ---------------------------------------------------------------------------

class TestReminderSettings:

    def test_get_default_settings(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/reminder-settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reminder_days_before_deadline"] == 1
        assert data["reminder_time_deadline"] == "09:00"
        assert data["reminder_days_before_shift"] == 1
        assert data["reminder_time_shift"] == "21:00"

    def test_update_settings(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put("/api/admin/reminder-settings", json={
            "reminder_days_before_deadline": 3,
            "reminder_time_deadline": "10:00",
            "reminder_days_before_shift": 2,
            "reminder_time_shift": "20:00",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reminder_days_before_deadline"] == 3
        assert data["reminder_time_deadline"] == "10:00"
        assert data["reminder_days_before_shift"] == 2
        assert data["reminder_time_shift"] == "20:00"

    def test_settings_persist(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.put("/api/admin/reminder-settings", json={
            "reminder_days_before_deadline": 5,
        })
        resp = client.get("/api/admin/reminder-settings")
        assert resp.get_json()["reminder_days_before_deadline"] == 5

    def test_partial_update(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Update only one field
        client.put("/api/admin/reminder-settings", json={
            "reminder_time_shift": "18:00",
        })
        resp = client.get("/api/admin/reminder-settings")
        data = resp.get_json()
        # Default for others
        assert data["reminder_days_before_deadline"] == 1
        assert data["reminder_time_shift"] == "18:00"


# ---------------------------------------------------------------------------
# Submission Reminders
# ---------------------------------------------------------------------------

class TestSubmissionReminders:

    def _setup_open_period(self, db_session, org, admin_user):
        """Create an open period with a deadline in the near future."""
        period = ShiftPeriod(
            organization_id=org.id,
            name="Test Period",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            submission_deadline=datetime.utcnow() + timedelta(hours=12),
            status="open",
            created_by=admin_user.id,
        )
        db_session.add(period)
        db_session.flush()
        return period

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_manual_send_reminder(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period = self._setup_open_period(db_session, org, admin_user)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post(f"/api/admin/reminders/send/{period.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sent"] == 1
        assert data["skipped"] == 0

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_dedup_reminder(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period = self._setup_open_period(db_session, org, admin_user)
        db_session.commit()
        auth.login_as(admin_user)

        # First send
        resp1 = client.post(f"/api/admin/reminders/send/{period.id}")
        assert resp1.get_json()["sent"] == 1

        # Second send — should be skipped due to dedup
        resp2 = client.post(f"/api/admin/reminders/send/{period.id}")
        assert resp2.get_json()["sent"] == 0
        assert resp2.get_json()["skipped"] == 1

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_skip_submitted_workers(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period = self._setup_open_period(db_session, org, admin_user)
        # Worker already submitted
        sub = ShiftSubmission(
            shift_period_id=period.id,
            user_id=worker_user.id,
            status="submitted",
            submitted_at=datetime.utcnow(),
        )
        db_session.add(sub)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post(f"/api/admin/reminders/send/{period.id}")
        assert resp.get_json()["sent"] == 0
        assert resp.get_json()["skipped"] == 1

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_auto_submission_reminders(self, mock_send, app, admin_user, org, worker_user, db_session):
        """Test the cron-triggered auto reminder check."""
        # Set org trigger to 0 days before (trigger immediately)
        org.set_setting("reminder_days_before_deadline", 0)
        period = ShiftPeriod(
            organization_id=org.id,
            name="Auto Period",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            submission_deadline=datetime.utcnow() + timedelta(hours=1),
            status="open",
            created_by=admin_user.id,
        )
        db_session.add(period)
        db_session.commit()

        from app.services.reminder_service import check_and_send_submission_reminders
        with app.app_context():
            result = check_and_send_submission_reminders()
        assert result["sent"] == 1

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_preshift_reminder(self, mock_send, app, admin_user, org, worker_user, db_session):
        """Test pre-shift reminder for workers with confirmed schedule entries."""
        org.set_setting("reminder_days_before_shift", 1)
        org.set_setting("reminder_time_shift", "00:00")

        period = ShiftPeriod(
            organization_id=org.id,
            name="Preshift Period",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            status="closed",
            created_by=admin_user.id,
        )
        db_session.add(period)
        db_session.flush()

        schedule = ShiftSchedule(
            shift_period_id=period.id,
            status="confirmed",
            created_by=admin_user.id,
        )
        db_session.add(schedule)
        db_session.flush()

        tomorrow = datetime.utcnow().date() + timedelta(days=1)
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=worker_user.id,
            shift_date=tomorrow,
            start_time="09:00",
            end_time="17:00",
        )
        db_session.add(entry)
        db_session.commit()

        from app.services.reminder_service import check_and_send_preshift_reminders
        with app.app_context():
            result = check_and_send_preshift_reminders()
        assert result["sent"] == 1


# ---------------------------------------------------------------------------
# Reminder Stats
# ---------------------------------------------------------------------------

class TestReminderStats:

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_get_stats(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period = ShiftPeriod(
            organization_id=org.id,
            name="Stats Period",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            submission_deadline=datetime.utcnow() + timedelta(hours=12),
            status="open",
            created_by=admin_user.id,
        )
        db_session.add(period)
        db_session.commit()
        auth.login_as(admin_user)

        # Send reminder first
        client.post(f"/api/admin/reminders/send/{period.id}")

        resp = client.get(f"/api/admin/reminders/stats/{period.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_workers"] == 1
        assert data["submitted_count"] == 0
        assert data["unsubmitted_count"] == 1
        assert data["reminders_sent"] == 1
        assert data["last_sent_at"] is not None

    def test_stats_not_found(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/reminders/stats/9999")
        assert resp.status_code == 404
