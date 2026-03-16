"""Tests for the approval workflow state machine.

Expected flow:  draft → pending_approval → approved → confirmed
                                         ↘ rejected (→ draft on re-edit)
"""

import pytest
from datetime import datetime

from app.extensions import db
from app.models.approval import ApprovalHistory
from app.models.shift import ShiftSchedule, ShiftScheduleEntry


class TestSubmitForApproval:
    """Admin submits schedule: draft → pending_approval."""

    def test_submit_draft_schedule(self, client, auth, admin_user, schedule, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/submit")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "pending_approval"

        # Audit trail
        history = ApprovalHistory.query.filter_by(schedule_id=schedule.id).all()
        assert len(history) == 1
        assert history[0].action == "submitted"

    def test_submit_non_draft_fails(self, client, auth, admin_user, schedule, db_session):
        schedule.status = "pending_approval"
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/submit")
        assert resp.status_code == 400


class TestOwnerApprove:
    """Owner approves: pending_approval → approved."""

    def test_approve_pending_schedule(self, client, auth, owner_user, schedule, db_session):
        schedule.status = "pending_approval"
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.post(
            f"/api/owner/schedules/{schedule.id}/approve",
            json={"comment": "Looks good"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "approved"
        assert data["approved_by"] == owner_user.id

        history = ApprovalHistory.query.filter_by(schedule_id=schedule.id, action="approved").first()
        assert history is not None
        assert history.comment == "Looks good"

    def test_approve_non_pending_fails(self, client, auth, owner_user, schedule, db_session):
        schedule.status = "draft"
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.post(f"/api/owner/schedules/{schedule.id}/approve")
        # Returns 400 (invalid state) — the owner endpoint first checks org access,
        # then delegates to approve_schedule which validates status
        assert resp.status_code == 400


class TestOwnerReject:
    """Owner rejects: pending_approval → rejected."""

    def test_reject_pending_schedule(self, client, auth, owner_user, schedule, db_session):
        schedule.status = "pending_approval"
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.post(
            f"/api/owner/schedules/{schedule.id}/reject",
            json={"comment": "Need changes"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Need changes"

    def test_reject_non_pending_fails(self, client, auth, owner_user, schedule, db_session):
        schedule.status = "approved"
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.post(f"/api/owner/schedules/{schedule.id}/reject")
        assert resp.status_code == 400


class TestConfirmSchedule:
    """Admin confirms approved schedule: approved → confirmed."""

    def test_confirm_approved_schedule(self, client, auth, admin_user, schedule, db_session):
        schedule.status = "approved"
        db_session.commit()
        auth.login_as(admin_user)

        # Mock calendar sync (requires Google credentials)
        from unittest.mock import patch
        with patch("app.blueprints.api_admin.get_credentials_for_user", return_value=None):
            resp = client.post(
                f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm"
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "confirmed"

        history = ApprovalHistory.query.filter_by(schedule_id=schedule.id, action="confirmed").first()
        assert history is not None

    def test_confirm_non_approved_fails(self, client, auth, admin_user, schedule, db_session):
        schedule.status = "pending_approval"
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")
        assert resp.status_code == 400


class TestCalendarSyncBehavior:
    """Calendar sync: no admin fallback, structured error codes."""

    def _make_entry(self, db_session, schedule, worker_user):
        from datetime import date
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=worker_user.id,
            shift_date=date(2026, 3, 10),
            start_time="09:00",
            end_time="17:00",
        )
        db_session.add(entry)
        db_session.flush()
        return entry

    def test_confirm_no_admin_fallback(self, client, auth, admin_user, worker_user, schedule, db_session):
        """Worker credentials None → needs_worker_action, no admin fallback."""
        schedule.status = "approved"
        entry = self._make_entry(db_session, schedule, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        from unittest.mock import patch
        with patch("app.blueprints.api_admin.get_credentials_for_user", return_value=None):
            resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "confirmed"

        sync_results = data["sync_results"]
        assert len(sync_results) == 1
        assert sync_results[0]["errorCode"] == "NO_CREDENTIALS"
        assert sync_results[0]["needs_worker_action"] is True
        assert "success" not in sync_results[0]

        # sync_summary check
        assert data["sync_summary"]["synced"] == 0
        assert data["sync_summary"]["needs_worker_action"] == 1

    def test_confirm_partial_sync(self, client, auth, admin_user, worker_user, schedule, db_session):
        """One worker with creds (success), one without (needs_worker_action)."""
        from app.models.user import User
        from app.models.membership import OrganizationMember
        # Create a second worker
        org_id = schedule.period.organization_id
        worker2 = User(google_id="gid_worker2@test.com", email="worker2@test.com",
                        display_name="Worker2", role="worker", organization_id=org_id)
        db_session.add(worker2)
        db_session.flush()
        db_session.add(OrganizationMember(
            user_id=worker2.id,
            organization_id=org_id,
            role="worker",
        ))
        db_session.flush()

        schedule.status = "approved"
        self._make_entry(db_session, schedule, worker_user)

        from datetime import date
        entry2 = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=worker2.id,
            shift_date=date(2026, 3, 11),
            start_time="10:00",
            end_time="18:00",
        )
        db_session.add(entry2)
        db_session.commit()
        auth.login_as(admin_user)

        fake_creds = object()  # truthy sentinel

        def side_effect(user):
            if user.id == worker_user.id:
                return fake_creds
            return None

        from unittest.mock import patch, MagicMock
        with patch("app.blueprints.api_admin.get_credentials_for_user", side_effect=side_effect), \
             patch("app.blueprints.api_admin.create_event", return_value="evt_123"):
            resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")

        assert resp.status_code == 200
        data = resp.get_json()
        summary = data["sync_summary"]
        assert summary["synced"] == 1
        assert summary["needs_worker_action"] == 1

    def test_confirm_credentials_expired(self, client, auth, admin_user, worker_user, schedule, db_session):
        """CredentialsExpiredError → errorCode CREDENTIALS_EXPIRED."""
        schedule.status = "approved"
        self._make_entry(db_session, schedule, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        from unittest.mock import patch
        from app.services.auth_service import CredentialsExpiredError
        with patch("app.blueprints.api_admin.get_credentials_for_user",
                    side_effect=CredentialsExpiredError("expired")):
            resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sync_results"][0]["errorCode"] == "CREDENTIALS_EXPIRED"
        assert data["sync_results"][0]["needs_worker_action"] is True

    def test_sync_error_persisted(self, client, auth, admin_user, worker_user, schedule, db_session):
        """sync_error is saved to ShiftScheduleEntry."""
        schedule.status = "approved"
        entry = self._make_entry(db_session, schedule, worker_user)
        db_session.commit()
        entry_id = entry.id
        auth.login_as(admin_user)

        from unittest.mock import patch
        with patch("app.blueprints.api_admin.get_credentials_for_user", return_value=None):
            resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")

        assert resp.status_code == 200
        # Re-fetch entry from DB
        persisted = db_session.get(ShiftScheduleEntry, entry_id)
        assert persisted.sync_error == "NO_CREDENTIALS"
        assert persisted.calendar_event_id is None

    def test_no_duplicate_events_on_retry(self, client, auth, admin_user, worker_user, schedule, db_session):
        """Already-synced entries (calendar_event_id set) are skipped on re-sync."""
        from datetime import date
        schedule.status = "approved"
        entry = self._make_entry(db_session, schedule, worker_user)
        # Simulate a previously synced entry
        entry.calendar_event_id = "existing_evt_001"
        entry.synced_at = datetime(2026, 3, 15, 12, 0, 0)
        entry.sync_error = None
        db_session.commit()
        auth.login_as(admin_user)

        from unittest.mock import patch, MagicMock
        mock_create = MagicMock()
        with patch("app.blueprints.api_admin.get_credentials_for_user", return_value=object()), \
             patch("app.blueprints.api_admin.create_event", mock_create):
            resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm")

        # confirm itself fails because schedule is already confirmed after first call,
        # but we need to test via _sync_schedule_to_calendar directly.
        # Instead: the schedule status is 'approved', so confirm transitions to 'confirmed'.
        assert resp.status_code == 200
        data = resp.get_json()

        # create_event should NOT have been called — entry was already synced
        mock_create.assert_not_called()

        # Result should show success with skipped flag
        sync_results = data["sync_results"]
        assert len(sync_results) == 1
        assert sync_results[0]["success"] is True
        assert sync_results[0]["skipped"] is True
        assert sync_results[0]["event_id"] == "existing_evt_001"


class TestFullWorkflow:
    """End-to-end: draft → pending_approval → approved → confirmed."""

    def test_full_happy_path(self, client, auth, admin_user, owner_user, schedule, db_session):
        db_session.commit()

        # 1. Admin submits
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/submit")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "pending_approval"

        # 2. Owner approves
        auth.login_as(owner_user)
        resp = client.post(
            f"/api/owner/schedules/{schedule.id}/approve",
            json={"comment": "Approved"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "approved"

        # 3. Admin confirms
        auth.login_as(admin_user)
        from unittest.mock import patch
        with patch("app.blueprints.api_admin.get_credentials_for_user", return_value=None):
            resp = client.post(
                f"/api/admin/periods/{schedule.shift_period_id}/schedule/confirm"
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "confirmed"

        # Verify complete audit trail
        history = ApprovalHistory.query.filter_by(schedule_id=schedule.id).order_by(
            ApprovalHistory.id
        ).all()
        actions = [h.action for h in history]
        assert actions == ["submitted", "approved", "confirmed"]

    def test_reject_then_resubmit(self, client, auth, admin_user, owner_user, schedule, db_session):
        db_session.commit()

        # 1. Admin submits
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/submit")

        # 2. Owner rejects
        auth.login_as(owner_user)
        resp = client.post(
            f"/api/owner/schedules/{schedule.id}/reject",
            json={"comment": "Fix shifts"},
        )
        assert resp.get_json()["status"] == "rejected"

        # 3. Admin re-saves schedule (creates new one since current is rejected)
        #    The system allows re-submitting if the schedule goes back to draft
        schedule.status = "draft"
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{schedule.shift_period_id}/schedule/submit")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "pending_approval"
