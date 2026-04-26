"""Tests for ShiftPeriod archive/unarchive and full delete with cleanup."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.reminder import Reminder
from app.models.vacancy import VacancyRequest, VacancyCandidate, ShiftChangeLog
from app.models.audit_log import AuditLog
from tests.conftest import _make_user


# ---------------------------------------------------------------------------
# Archive / Unarchive
# ---------------------------------------------------------------------------

class TestArchive:

    def test_archive_sets_flag_and_timestamp(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post(f"/api/admin/periods/{period.id}/archive")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_archived"] is True
        assert data["archived_at"] is not None

    def test_archive_is_idempotent(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/archive")
        # Second call should also return 200
        resp = client.post(f"/api/admin/periods/{period.id}/archive")
        assert resp.status_code == 200
        assert resp.get_json()["is_archived"] is True

    def test_unarchive_clears_flag(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/archive")
        resp = client.post(f"/api/admin/periods/{period.id}/unarchive")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_archived"] is False
        assert data["archived_at"] is None

    def test_unarchive_is_idempotent(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Period starts unarchived; calling unarchive should still 200
        resp = client.post(f"/api/admin/periods/{period.id}/unarchive")
        assert resp.status_code == 200
        assert resp.get_json()["is_archived"] is False

    def test_archive_writes_audit_log(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/archive")
        log = AuditLog.query.filter_by(action="PERIOD_ARCHIVED", resource_id=period.id).first()
        assert log is not None
        assert log.actor_id == admin_user.id

    def test_archive_returns_404_for_other_org(self, client, auth, db_session):
        from tests.conftest import _make_org
        org_a = _make_org(db_session, name="A")
        org_b = _make_org(db_session, name="B")
        admin_a = _make_user(db_session, org_a, email="a@x.com", role="admin")
        admin_b = _make_user(db_session, org_b, email="b@x.com", role="admin")
        period_a = ShiftPeriod(
            organization_id=org_a.id, name="P", start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31), status="draft", created_by=admin_a.id,
        )
        db_session.add(period_a)
        db_session.commit()
        auth.login_as(admin_b)
        resp = client.post(f"/api/admin/periods/{period_a.id}/archive")
        assert resp.status_code == 404

    def test_non_admin_cannot_archive(self, client, auth, worker_user, period, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.post(f"/api/admin/periods/{period.id}/archive")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# include_archived filter on GET /periods
# ---------------------------------------------------------------------------

class TestListFilter:

    def test_archived_excluded_by_default(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/archive")
        resp = client.get("/api/admin/periods")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.get_json()]
        assert period.id not in ids

    def test_archived_included_when_flag_true(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.post(f"/api/admin/periods/{period.id}/archive")
        resp = client.get("/api/admin/periods?include_archived=true")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.get_json()]
        assert period.id in ids

    def test_active_period_visible_in_default_list(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/periods")
        ids = [p["id"] for p in resp.get_json()]
        assert period.id in ids


# ---------------------------------------------------------------------------
# Impact summary
# ---------------------------------------------------------------------------

class TestImpactSummary:

    def test_empty_period_has_zero_counts(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get(f"/api/admin/periods/{period.id}/impact")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["submissions"] == 0
        assert data["entries"] == 0
        assert data["synced_entries"] == 0
        assert data["vacancies"] == 0

    def test_counts_reflect_actual_data(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        # Submission
        sub = ShiftSubmission(
            shift_period_id=period.id, user_id=worker_user.id, status="submitted",
        )
        db_session.add(sub)
        # Entry with calendar sync
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
            calendar_event_id="evt_abc",
        )
        db_session.add(entry)
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get(f"/api/admin/periods/{period.id}/impact")
        data = resp.get_json()
        assert data["submissions"] == 1
        assert data["entries"] == 1
        assert data["synced_entries"] == 1


# ---------------------------------------------------------------------------
# Delete period (full cleanup)
# ---------------------------------------------------------------------------

def _archive(period, db_session):
    """テスト用ヘルパー: アーカイブ必須ガードを通過させるため事前に archive する。"""
    period.is_archived = True
    period.archived_at = datetime.utcnow()
    db_session.commit()


class TestDeleteGuard:

    def test_delete_rejected_when_not_archived(self, client, auth, admin_user, period, db_session):
        """フェールセーフ: 未アーカイブの period は削除を拒否する。"""
        db_session.commit()
        period_id = period.id
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/periods/{period_id}")
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "ARCHIVE_REQUIRED"
        # Period still exists
        assert db.session.get(ShiftPeriod, period_id) is not None


class TestDelete:

    def test_delete_basic_period(self, client, auth, admin_user, period, db_session):
        _archive(period, db_session)
        period_id = period.id
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/periods/{period_id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert db.session.get(ShiftPeriod, period_id) is None

    def test_delete_cascades_submissions(self, client, auth, admin_user, period, worker_user, db_session):
        sub = ShiftSubmission(
            shift_period_id=period.id, user_id=worker_user.id, status="submitted",
        )
        db_session.add(sub)
        db_session.flush()
        slot = ShiftSubmissionSlot(
            submission_id=sub.id, slot_date=date(2026, 3, 5), is_available=True,
        )
        db_session.add(slot)
        _archive(period, db_session)
        sub_id, slot_id = sub.id, slot.id
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/periods/{period.id}")
        assert resp.status_code == 200
        assert db.session.get(ShiftSubmission, sub_id) is None
        assert db.session.get(ShiftSubmissionSlot, slot_id) is None

    def test_delete_cascades_schedule_and_entries(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
        )
        db_session.add(entry)
        _archive(period, db_session)
        sched_id, entry_id = schedule.id, entry.id
        auth.login_as(admin_user)
        client.delete(f"/api/admin/periods/{period.id}")
        assert db.session.get(ShiftSchedule, sched_id) is None
        assert db.session.get(ShiftScheduleEntry, entry_id) is None

    def test_delete_cleans_reminders(self, client, auth, admin_user, period, schedule, worker_user, db_session, org):
        # Reminder for submission_deadline → reference_id = period.id
        r1 = Reminder(
            organization_id=org.id, reminder_type="submission_deadline",
            reference_id=period.id, user_id=worker_user.id,
        )
        # Reminder for preshift → reference_id = entry.id
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
        )
        db_session.add(entry)
        db_session.flush()
        r2 = Reminder(
            organization_id=org.id, reminder_type="preshift",
            reference_id=entry.id, user_id=worker_user.id,
        )
        db_session.add_all([r1, r2])
        _archive(period, db_session)
        r1_id, r2_id = r1.id, r2.id
        auth.login_as(admin_user)
        client.delete(f"/api/admin/periods/{period.id}")
        assert db.session.get(Reminder, r1_id) is None
        assert db.session.get(Reminder, r2_id) is None

    def test_delete_cleans_vacancies_and_change_logs(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
        )
        db_session.add(entry)
        db_session.flush()
        vr = VacancyRequest(
            schedule_entry_id=entry.id, original_user_id=worker_user.id,
            status="open", created_by=admin_user.id,
        )
        db_session.add(vr)
        db_session.flush()
        vc = VacancyCandidate(
            vacancy_request_id=vr.id, user_id=worker_user.id, status="pending",
        )
        cl = ShiftChangeLog(
            schedule_entry_id=entry.id, vacancy_request_id=vr.id,
            change_type="vacancy_fill", original_user_id=worker_user.id,
            new_user_id=worker_user.id, performed_by=admin_user.id,
        )
        db_session.add_all([vc, cl])
        _archive(period, db_session)
        vr_id, vc_id, cl_id = vr.id, vc.id, cl.id
        auth.login_as(admin_user)
        resp = client.delete(f"/api/admin/periods/{period.id}")
        assert resp.status_code == 200
        assert db.session.get(VacancyRequest, vr_id) is None
        assert db.session.get(VacancyCandidate, vc_id) is None
        assert db.session.get(ShiftChangeLog, cl_id) is None

    def test_delete_attempts_calendar_cleanup(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        """Synced entries should trigger best-effort calendar deletion."""
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
            calendar_event_id="evt_xyz",
        )
        db_session.add(entry)
        _archive(period, db_session)
        period_id = period.id
        auth.login_as(admin_user)
        # Mock get_credentials_for_user to return None → cleanup skipped (best-effort)
        with patch("app.services.auth_service.get_credentials_for_user", return_value=None):
            resp = client.delete(f"/api/admin/periods/{period_id}")
        assert resp.status_code == 200
        summary = resp.get_json()["cleanup_summary"]
        assert summary["calendar_events_deleted"] == 0
        assert summary["calendar_events_failed"] == 0
        assert summary["calendar_events_skipped"] == 1
        # DB delete still proceeds
        assert db.session.get(ShiftPeriod, period_id) is None

    def test_delete_calendar_success_path(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        """When credentials are available and delete_event succeeds, count increments."""
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
            calendar_event_id="evt_xyz",
        )
        db_session.add(entry)
        _archive(period, db_session)
        auth.login_as(admin_user)
        with patch("app.services.auth_service.get_credentials_for_user", return_value="fake_cred"), \
             patch("app.services.calendar_service.delete_event") as mock_del:
            resp = client.delete(f"/api/admin/periods/{period.id}")
        assert resp.status_code == 200
        summary = resp.get_json()["cleanup_summary"]
        assert summary["calendar_events_deleted"] == 1
        assert summary["calendar_events_failed"] == 0
        assert summary["calendar_events_skipped"] == 0
        mock_del.assert_called_once()

    def test_delete_calendar_failure_path(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        """delete_event が例外を投げた場合は failed カウンタが増え、DB 削除は続行する。"""
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
            calendar_event_id="evt_xyz",
        )
        db_session.add(entry)
        _archive(period, db_session)
        period_id = period.id
        auth.login_as(admin_user)
        with patch("app.services.auth_service.get_credentials_for_user", return_value="fake_cred"), \
             patch("app.services.calendar_service.delete_event", side_effect=RuntimeError("API down")):
            resp = client.delete(f"/api/admin/periods/{period_id}")
        assert resp.status_code == 200
        summary = resp.get_json()["cleanup_summary"]
        assert summary["calendar_events_deleted"] == 0
        assert summary["calendar_events_failed"] == 1
        assert summary["calendar_events_skipped"] == 0
        assert db.session.get(ShiftPeriod, period_id) is None

    def test_delete_writes_audit_log(self, client, auth, admin_user, period, db_session):
        _archive(period, db_session)
        period_id = period.id
        auth.login_as(admin_user)
        client.delete(f"/api/admin/periods/{period_id}")
        log = AuditLog.query.filter_by(action="PERIOD_DELETED", resource_id=period_id).first()
        assert log is not None
        assert log.actor_id == admin_user.id

    def test_delete_returns_404_for_other_org(self, client, auth, db_session):
        from tests.conftest import _make_org
        org_a = _make_org(db_session, name="A")
        org_b = _make_org(db_session, name="B")
        admin_a = _make_user(db_session, org_a, email="a@x.com", role="admin")
        admin_b = _make_user(db_session, org_b, email="b@x.com", role="admin")
        period_a = ShiftPeriod(
            organization_id=org_a.id, name="P", start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31), status="draft", created_by=admin_a.id,
            is_archived=True, archived_at=datetime.utcnow(),
        )
        db_session.add(period_a)
        db_session.commit()
        auth.login_as(admin_b)
        resp = client.delete(f"/api/admin/periods/{period_a.id}")
        assert resp.status_code == 404
        # Not deleted
        assert db.session.get(ShiftPeriod, period_a.id) is not None

    def test_non_admin_cannot_delete(self, client, auth, worker_user, period, db_session):
        _archive(period, db_session)
        auth.login_as(worker_user)
        resp = client.delete(f"/api/admin/periods/{period.id}")
        assert resp.status_code == 403
        # Still exists
        assert db.session.get(ShiftPeriod, period.id) is not None


# ---------------------------------------------------------------------------
# Confirm response includes period info for archive prompt
# ---------------------------------------------------------------------------

class TestConfirmResponse:

    def test_confirm_response_includes_period(self, client, auth, admin_user, period, schedule, worker_user, db_session):
        """Confirm endpoint should include period info so frontend can show archive prompt."""
        # Schedule must be in 'approved' state for confirm() (or use direct path with approval_required=False)
        # Default org has no approval_required setting → direct path applies
        entry = ShiftScheduleEntry(
            schedule_id=schedule.id, user_id=worker_user.id,
            shift_date=date(2026, 3, 5), start_time="09:00", end_time="17:00",
        )
        db_session.add(entry)
        db_session.commit()
        auth.login_as(admin_user)
        # Mock calendar sync to avoid actual API calls
        with patch("app.blueprints.api_admin._sync_schedule_to_calendar", return_value=[]):
            resp = client.post(f"/api/admin/periods/{period.id}/schedule/confirm")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "period" in data
        assert data["period"]["id"] == period.id
        assert data["period"]["name"] == period.name
        assert data["period"]["is_archived"] is False
