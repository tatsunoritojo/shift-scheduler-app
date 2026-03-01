"""Tests for input validation across API endpoints."""

import pytest


class TestOpeningHoursValidation:
    """PUT /api/admin/opening-hours validation."""

    def test_rejects_non_array_body(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put("/api/admin/opening-hours", json={"not": "array"})
        assert resp.status_code == 400

    def test_rejects_invalid_time_format(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put("/api/admin/opening-hours", json=[
            {"day_of_week": 0, "start_time": "9:00", "end_time": "17:00"}
        ])
        assert resp.status_code == 400
        assert "HH:MM" in resp.get_json()["error"]

    def test_accepts_valid_hours(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put("/api/admin/opening-hours", json=[
            {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00", "is_closed": False}
        ])
        assert resp.status_code == 200


class TestExceptionValidation:
    """POST /api/admin/opening-hours/exceptions validation."""

    def test_rejects_missing_date(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={})
        assert resp.status_code == 400

    def test_rejects_invalid_date_format(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={
            "exception_date": "not-a-date"
        })
        assert resp.status_code == 400

    def test_rejects_invalid_source(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={
            "exception_date": "2026-03-15",
            "source": "invalid",
        })
        assert resp.status_code == 400

    def test_rejects_invalid_time_in_exception(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={
            "exception_date": "2026-03-15",
            "start_time": "25:00",
        })
        assert resp.status_code == 400

    def test_rejects_overly_long_reason(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={
            "exception_date": "2026-03-15",
            "reason": "x" * 2001,
        })
        assert resp.status_code == 400

    def test_accepts_valid_exception(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/opening-hours/exceptions", json={
            "exception_date": "2026-03-15",
            "is_closed": True,
            "reason": "Holiday",
        })
        assert resp.status_code == 201


class TestPeriodValidation:
    """POST /api/admin/periods validation."""

    def test_rejects_empty_body(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", content_type="application/json")
        assert resp.status_code == 400

    def test_rejects_missing_dates(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={"name": "Test"})
        assert resp.status_code == 400

    def test_rejects_start_after_end(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "Bad Range",
            "start_date": "2026-04-01",
            "end_date": "2026-03-01",
        })
        assert resp.status_code == 400

    def test_rejects_missing_name(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
        })
        assert resp.status_code == 400

    def test_rejects_overly_long_name(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "x" * 201,
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
        })
        assert resp.status_code == 400

    def test_accepts_valid_period(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "April 2026",
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "April 2026"
        assert data["status"] == "draft"


class TestPeriodUpdateValidation:
    """PUT /api/admin/periods/<id> validation."""

    def test_rejects_invalid_status(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/periods/{period.id}", json={
            "status": "invalid_status"
        })
        assert resp.status_code == 400

    def test_rejects_start_after_end_on_update(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/periods/{period.id}", json={
            "start_date": "2026-12-01",
            "end_date": "2026-01-01",
        })
        assert resp.status_code == 400

    def test_accepts_valid_update(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/periods/{period.id}", json={
            "name": "Updated Name",
            "status": "open",
        })
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Updated Name"
        assert resp.get_json()["status"] == "open"


class TestWorkerSubmissionValidation:
    """POST /api/worker/periods/<id>/availability validation."""

    def test_rejects_when_period_not_open(self, client, auth, worker_user, period, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.post(f"/api/worker/periods/{period.id}/availability", json={
            "slots": [],
        })
        assert resp.status_code == 400
        assert "not open" in resp.get_json()["error"]

    def test_rejects_nonexistent_period(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.post("/api/worker/periods/99999/availability", json={
            "slots": [],
        })
        assert resp.status_code == 404

    def test_rejects_empty_body(self, client, auth, worker_user, period, db_session):
        period.status = "open"
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.post(
            f"/api/worker/periods/{period.id}/availability",
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestValidatorUnit:
    """Unit tests for validator functions."""

    def test_validate_time_str_valid(self):
        from app.utils.validators import validate_time_str
        validate_time_str("00:00", "start")
        validate_time_str("23:59", "end")
        validate_time_str("12:30", "mid")

    @pytest.mark.parametrize("value", ["25:00", "9:00", "12:60", "", "abc", "12:0", "1200"])
    def test_validate_time_str_invalid(self, value):
        from app.utils.validators import validate_time_str
        with pytest.raises(ValueError):
            validate_time_str(value, "field")

    def test_validate_time_str_none(self):
        from app.utils.validators import validate_time_str
        with pytest.raises(ValueError):
            validate_time_str(None, "field")

    def test_validate_text_length_none_allowed(self):
        from app.utils.validators import validate_text_length
        validate_text_length(None, "field", 100)  # should not raise

    def test_validate_text_length_within_limit(self):
        from app.utils.validators import validate_text_length
        validate_text_length("hello", "field", 10)

    def test_validate_text_length_exceeds_limit(self):
        from app.utils.validators import validate_text_length
        with pytest.raises(ValueError):
            validate_text_length("x" * 11, "field", 10)

    def test_validate_text_length_non_string(self):
        from app.utils.validators import validate_text_length
        with pytest.raises(ValueError):
            validate_text_length(123, "field", 10)

    def test_parse_date_valid(self):
        from app.utils.validators import parse_date
        from datetime import date
        assert parse_date("2026-03-01") == date(2026, 3, 1)

    def test_parse_date_invalid(self):
        from app.utils.validators import parse_date
        assert parse_date("not-a-date") is None
        assert parse_date(None) is None

    def test_parse_time_valid(self):
        from app.utils.validators import parse_time
        from datetime import time
        assert parse_time("09:30") == time(9, 30)

    def test_parse_time_invalid(self):
        from app.utils.validators import parse_time
        assert parse_time("invalid") is None
        assert parse_time(None) is None
