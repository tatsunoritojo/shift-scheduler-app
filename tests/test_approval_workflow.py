"""Tests for the approval workflow state machine.

Expected flow:  draft → pending_approval → approved → confirmed
                                         ↘ rejected (→ draft on re-edit)
"""

import pytest

from app.extensions import db
from app.models.approval import ApprovalHistory
from app.models.shift import ShiftSchedule


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
