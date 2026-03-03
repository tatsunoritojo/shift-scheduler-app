"""Tests for the operational dashboard API."""

from datetime import datetime, timedelta

import pytest

from app.models.async_task import AsyncTask
from app.models.shift import ShiftSchedule


class TestDashboardOverview:
    """GET /api/admin/dashboard/overview."""

    def test_returns_overview(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/overview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tasks' in data
        assert 'approvals' in data
        assert 'recent_syncs' in data

    def test_requires_admin(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get('/api/admin/dashboard/overview')
        assert resp.status_code == 403

    def test_shows_task_counts(self, client, auth, admin_user, org, db_session):
        # Create some tasks
        for status in ['completed', 'completed', 'dead']:
            task = AsyncTask(
                task_type='send_email',
                payload={},
                status=status,
                organization_id=org.id,
            )
            db_session.add(task)
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/overview')
        data = resp.get_json()
        assert data['tasks']['last_24h'].get('completed', 0) == 2
        assert data['tasks']['last_24h'].get('dead', 0) == 1


class TestDashboardTasks:
    """GET /api/admin/dashboard/tasks."""

    def test_lists_tasks(self, client, auth, admin_user, org, db_session):
        for i in range(3):
            db_session.add(AsyncTask(
                task_type='send_email',
                payload={},
                organization_id=org.id,
            ))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/tasks')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3

    def test_filters_by_status(self, client, auth, admin_user, org, db_session):
        db_session.add(AsyncTask(task_type='send_email', payload={}, status='pending', organization_id=org.id))
        db_session.add(AsyncTask(task_type='send_email', payload={}, status='completed', organization_id=org.id))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/tasks?status=pending')
        assert len(resp.get_json()) == 1

    def test_respects_limit(self, client, auth, admin_user, org, db_session):
        for _ in range(10):
            db_session.add(AsyncTask(task_type='send_email', payload={}, organization_id=org.id))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/tasks?limit=3')
        assert len(resp.get_json()) == 3

    def test_isolates_by_org(self, client, auth, admin_user, org, db_session):
        from tests.conftest import _make_org
        other_org = _make_org(db_session, name="Other Org")
        db_session.add(AsyncTask(task_type='send_email', payload={}, organization_id=other_org.id))
        db_session.add(AsyncTask(task_type='send_email', payload={}, organization_id=org.id))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/tasks')
        assert len(resp.get_json()) == 1  # only own org


class TestDashboardTaskStats:
    """GET /api/admin/dashboard/task-stats."""

    def test_returns_stats_by_type(self, client, auth, admin_user, org, db_session):
        db_session.add(AsyncTask(task_type='send_email', payload={}, status='completed', organization_id=org.id))
        db_session.add(AsyncTask(task_type='send_email', payload={}, status='dead', organization_id=org.id))
        db_session.add(AsyncTask(task_type='sync_calendar_event', payload={}, status='completed', organization_id=org.id))
        db_session.commit()

        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/task-stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'send_email' in data['by_type']
        assert data['by_type']['send_email']['completed'] == 1
        assert data['by_type']['send_email']['dead'] == 1

    def test_custom_period(self, client, auth, admin_user, org, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/dashboard/task-stats?days=30')
        assert resp.status_code == 200
        assert resp.get_json()['period_days'] == 30
