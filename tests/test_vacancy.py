"""Tests for vacancy fill workflow — candidates, requests, notifications, responses."""

import secrets
from datetime import datetime, date, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.organization import Organization
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.vacancy import VacancyRequest, VacancyCandidate, ShiftChangeLog
from app.models.user import User
from tests.conftest import _make_org, _make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_schedule(db_session, org, admin_user, worker_user):
    """Create a confirmed schedule with one entry for the worker."""
    period = ShiftPeriod(
        organization_id=org.id,
        name="Vacancy Test Period",
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

    entry = ShiftScheduleEntry(
        schedule_id=schedule.id,
        user_id=worker_user.id,
        shift_date=date(2026, 4, 15),
        start_time="09:00",
        end_time="17:00",
    )
    db_session.add(entry)
    db_session.flush()

    return period, schedule, entry


def _create_candidate_worker(db_session, org, period, email="worker2@test.com"):
    """Create a second worker who submitted availability for the target date."""
    worker2 = _make_user(db_session, org, email=email, role="worker", display_name="Worker 2")
    sub = ShiftSubmission(
        shift_period_id=period.id,
        user_id=worker2.id,
        status="submitted",
        submitted_at=datetime.utcnow(),
    )
    db_session.add(sub)
    db_session.flush()

    slot = ShiftSubmissionSlot(
        submission_id=sub.id,
        slot_date=date(2026, 4, 15),
        is_available=True,
        start_time="09:00",
        end_time="17:00",
    )
    db_session.add(slot)
    db_session.flush()

    return worker2


# ---------------------------------------------------------------------------
# Candidate Search
# ---------------------------------------------------------------------------

class TestCandidateSearch:

    def test_find_candidates(self, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.get(f"/api/admin/vacancy/candidates/{entry.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["user_id"] == worker2.id

    def test_no_candidates_when_all_assigned(self, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        # Assign worker2 on the same date
        entry2 = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=worker2.id,
            shift_date=date(2026, 4, 15),
            start_time="09:00",
            end_time="17:00",
        )
        db_session.add(entry2)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.get(f"/api/admin/vacancy/candidates/{entry.id}")
        assert resp.get_json() == []

    def test_candidates_exclude_original_worker(self, client, auth, admin_user, org, worker_user, db_session):
        """Original worker should not appear in candidates even if they submitted availability."""
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        # Worker also submitted availability for the same date
        sub = ShiftSubmission(
            shift_period_id=period.id,
            user_id=worker_user.id,
            status="submitted",
        )
        db_session.add(sub)
        db_session.flush()
        slot = ShiftSubmissionSlot(
            submission_id=sub.id,
            slot_date=date(2026, 4, 15),
            is_available=True,
            start_time="09:00",
            end_time="17:00",
        )
        db_session.add(slot)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.get(f"/api/admin/vacancy/candidates/{entry.id}")
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# Vacancy Request CRUD
# ---------------------------------------------------------------------------

class TestVacancyRequest:

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_create_vacancy(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={
            "schedule_entry_id": entry.id,
            "reason": "体調不良",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "open"
        assert data["reason"] == "体調不良"

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_duplicate_vacancy_blocked(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        assert resp.status_code == 400

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_cancel_vacancy(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        vid = resp.get_json()["id"]

        resp = client.delete(f"/api/admin/vacancy/{vid}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cancelled"

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_list_vacancies(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        db_session.commit()
        auth.login_as(admin_user)

        client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        resp = client.get("/api/admin/vacancy")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1


# ---------------------------------------------------------------------------
# Notification & Response
# ---------------------------------------------------------------------------

class TestVacancyResponse:

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_notify_and_accept(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        db_session.commit()
        auth.login_as(admin_user)

        # Create vacancy
        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        vid = resp.get_json()["id"]

        # Notify candidates
        resp = client.post(f"/api/admin/vacancy/{vid}/notify", json={
            "candidate_user_ids": [worker2.id],
        })
        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 1

        # Get the response token
        candidate = VacancyCandidate.query.filter_by(
            vacancy_request_id=vid, user_id=worker2.id
        ).first()
        assert candidate is not None
        assert candidate.response_token is not None

        # Accept via public endpoint
        resp = client.get(f"/vacancy/respond?token={candidate.response_token}&action=accept")
        assert resp.status_code == 200
        assert "引き受けました" in resp.data.decode()

        # Verify entry was updated
        db_session.expire_all()
        updated_entry = db.session.get(ShiftScheduleEntry, entry.id)
        assert updated_entry.user_id == worker2.id

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_decline(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        vid = resp.get_json()["id"]
        client.post(f"/api/admin/vacancy/{vid}/notify", json={"candidate_user_ids": [worker2.id]})

        candidate = VacancyCandidate.query.filter_by(vacancy_request_id=vid, user_id=worker2.id).first()
        resp = client.get(f"/vacancy/respond?token={candidate.response_token}&action=decline")
        assert resp.status_code == 200
        assert "辞退しました" in resp.data.decode()

        # Entry should NOT change
        db_session.expire_all()
        updated_entry = db.session.get(ShiftScheduleEntry, entry.id)
        assert updated_entry.user_id == worker_user.id

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_race_condition_second_accept_blocked(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        """When two candidates try to accept, only the first should succeed."""
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period, email="worker2@test.com")
        worker3 = _create_candidate_worker(db_session, org, period, email="worker3@test.com")
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        vid = resp.get_json()["id"]
        client.post(f"/api/admin/vacancy/{vid}/notify", json={
            "candidate_user_ids": [worker2.id, worker3.id],
        })

        c2 = VacancyCandidate.query.filter_by(vacancy_request_id=vid, user_id=worker2.id).first()
        c3 = VacancyCandidate.query.filter_by(vacancy_request_id=vid, user_id=worker3.id).first()

        # Worker 2 accepts first
        resp1 = client.get(f"/vacancy/respond?token={c2.response_token}&action=accept")
        assert "引き受けました" in resp1.data.decode()

        # Worker 3 tries to accept — should be blocked
        resp2 = client.get(f"/vacancy/respond?token={c3.response_token}&action=accept")
        assert "補充済み" in resp2.data.decode()

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_all_decline_expires_vacancy(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id})
        vid = resp.get_json()["id"]
        client.post(f"/api/admin/vacancy/{vid}/notify", json={"candidate_user_ids": [worker2.id]})

        candidate = VacancyCandidate.query.filter_by(vacancy_request_id=vid, user_id=worker2.id).first()
        client.get(f"/vacancy/respond?token={candidate.response_token}&action=decline")

        db_session.expire_all()
        vacancy = db.session.get(VacancyRequest, vid)
        assert vacancy.status == "expired"

    def test_invalid_token(self, client):
        resp = client.get("/vacancy/respond?token=invalid&action=accept")
        assert resp.status_code == 200
        assert "無効" in resp.data.decode()

    def test_missing_params(self, client):
        resp = client.get("/vacancy/respond")
        assert resp.status_code == 200
        assert "無効" in resp.data.decode()


# ---------------------------------------------------------------------------
# Change Log
# ---------------------------------------------------------------------------

class TestChangeLog:

    @patch("app.services.notification_service._enqueue_or_send", return_value=True)
    def test_change_log_created_on_accept(self, mock_send, client, auth, admin_user, org, worker_user, db_session):
        period, schedule, entry = _setup_schedule(db_session, org, admin_user, worker_user)
        worker2 = _create_candidate_worker(db_session, org, period)
        db_session.commit()
        auth.login_as(admin_user)

        resp = client.post("/api/admin/vacancy", json={"schedule_entry_id": entry.id, "reason": "test"})
        vid = resp.get_json()["id"]
        client.post(f"/api/admin/vacancy/{vid}/notify", json={"candidate_user_ids": [worker2.id]})

        candidate = VacancyCandidate.query.filter_by(vacancy_request_id=vid, user_id=worker2.id).first()
        client.get(f"/vacancy/respond?token={candidate.response_token}&action=accept")

        resp = client.get("/api/admin/change-log")
        assert resp.status_code == 200
        logs = resp.get_json()
        assert len(logs) == 1
        assert logs[0]["change_type"] == "vacancy_fill"
        assert logs[0]["original_user_id"] == worker_user.id
        assert logs[0]["new_user_id"] == worker2.id

    def test_empty_change_log(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get("/api/admin/change-log")
        assert resp.status_code == 200
        assert resp.get_json() == []
