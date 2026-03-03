"""Tests for the async task queue and cron endpoint."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models.async_task import AsyncTask


class TestAsyncTaskModel:
    """Unit tests for AsyncTask model."""

    def test_create_task(self, db_session):
        task = AsyncTask(
            task_type='send_email',
            payload={'to_email': 'test@example.com', 'subject': 'Hi', 'body_html': '<p>Hi</p>'},
        )
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        assert task.status == 'pending'
        assert task.retry_count == 0

    def test_mark_running(self, db_session):
        task = AsyncTask(task_type='send_email', payload={})
        db_session.add(task)
        db_session.flush()
        task.mark_running()
        assert task.status == 'running'
        assert task.started_at is not None

    def test_mark_completed(self, db_session):
        task = AsyncTask(task_type='send_email', payload={})
        db_session.add(task)
        db_session.flush()
        task.mark_completed()
        assert task.status == 'completed'
        assert task.completed_at is not None

    def test_mark_failed_with_retries(self, db_session):
        task = AsyncTask(task_type='send_email', payload={}, max_retries=3)
        db_session.add(task)
        db_session.flush()

        task.mark_failed("SMTP error")
        assert task.status == 'pending'  # back to pending for retry
        assert task.retry_count == 1
        assert task.error_message == "SMTP error"
        assert task.next_run_at > datetime.utcnow()

    def test_mark_failed_exhausted(self, db_session):
        task = AsyncTask(task_type='send_email', payload={}, max_retries=2, retry_count=1)
        db_session.add(task)
        db_session.flush()

        task.mark_failed("Final failure")
        assert task.status == 'dead'
        assert task.retry_count == 2
        assert task.completed_at is not None

    def test_exponential_backoff(self, db_session):
        task = AsyncTask(task_type='send_email', payload={}, max_retries=5)
        db_session.add(task)
        db_session.flush()

        before = datetime.utcnow()
        task.mark_failed("error 1")
        # First retry: 30s delay
        assert task.next_run_at >= before + timedelta(seconds=25)

        task.mark_failed("error 2")
        # Second retry: 120s delay
        assert task.next_run_at >= before + timedelta(seconds=100)

    def test_to_dict(self, db_session):
        task = AsyncTask(task_type='send_email', payload={'key': 'value'})
        db_session.add(task)
        db_session.flush()
        d = task.to_dict()
        assert d['task_type'] == 'send_email'
        assert d['status'] == 'pending'
        assert 'id' in d


class TestTaskRunner:
    """Tests for process_pending_tasks."""

    def test_processes_pending_tasks(self, app, db_session):
        task = AsyncTask(
            task_type='send_email',
            payload={'to_email': 'a@b.com', 'subject': 'Test', 'body_html': '<p>hi</p>'},
        )
        db_session.add(task)
        db_session.commit()

        with patch('app.services.notification_service.send_email', return_value=True):
            from app.services.task_runner import process_pending_tasks
            stats = process_pending_tasks()

        assert stats['processed'] == 1
        assert stats['succeeded'] == 1

        refreshed = db_session.get(AsyncTask, task.id)
        assert refreshed.status == 'completed'

    def test_skips_future_tasks(self, app, db_session):
        task = AsyncTask(
            task_type='send_email',
            payload={'to_email': 'a@b.com', 'subject': 'Test', 'body_html': '<p>hi</p>'},
            next_run_at=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(task)
        db_session.commit()

        from app.services.task_runner import process_pending_tasks
        stats = process_pending_tasks()
        assert stats['processed'] == 0

    def test_retries_on_failure(self, app, db_session):
        task = AsyncTask(
            task_type='send_email',
            payload={'to_email': 'a@b.com', 'subject': 'Test', 'body_html': '<p>hi</p>'},
            max_retries=3,
        )
        db_session.add(task)
        db_session.commit()

        with patch('app.services.notification_service.send_email', return_value=False):
            from app.services.task_runner import process_pending_tasks
            stats = process_pending_tasks()

        assert stats['processed'] == 1
        assert stats['failed'] == 1

        refreshed = db_session.get(AsyncTask, task.id)
        assert refreshed.status == 'pending'
        assert refreshed.retry_count == 1

    def test_dead_letter_after_max_retries(self, app, db_session):
        task = AsyncTask(
            task_type='send_email',
            payload={'to_email': 'a@b.com', 'subject': 'Test', 'body_html': '<p>hi</p>'},
            max_retries=1,
            retry_count=0,
        )
        db_session.add(task)
        db_session.commit()

        with patch('app.services.notification_service.send_email', return_value=False):
            from app.services.task_runner import process_pending_tasks
            stats = process_pending_tasks()

        assert stats['dead'] == 1
        refreshed = db_session.get(AsyncTask, task.id)
        assert refreshed.status == 'dead'

    def test_unknown_task_type_goes_dead(self, app, db_session):
        task = AsyncTask(task_type='nonexistent', payload={})
        db_session.add(task)
        db_session.commit()

        from app.services.task_runner import process_pending_tasks
        stats = process_pending_tasks()

        assert stats['dead'] == 1
        refreshed = db_session.get(AsyncTask, task.id)
        assert refreshed.status == 'dead'

    def test_batch_size_limit(self, app, db_session):
        for i in range(5):
            db_session.add(AsyncTask(
                task_type='send_email',
                payload={'to_email': f'{i}@b.com', 'subject': 'T', 'body_html': ''},
            ))
        db_session.commit()

        with patch('app.services.notification_service.send_email', return_value=True):
            from app.services.task_runner import process_pending_tasks
            stats = process_pending_tasks(batch_size=3)

        assert stats['processed'] == 3
        assert stats['succeeded'] == 3


class TestEnqueueHelpers:
    """Test task creation helpers."""

    def test_enqueue_email(self, app, db_session):
        from app.services.task_runner import enqueue_email
        task = enqueue_email('test@example.com', 'Subject', '<p>Body</p>')
        db_session.commit()

        assert task.task_type == 'send_email'
        assert task.payload['to_email'] == 'test@example.com'
        assert task.status == 'pending'

    def test_enqueue_calendar_sync(self, app, db_session):
        from app.services.task_runner import enqueue_calendar_sync
        task = enqueue_calendar_sync(
            user_id=1,
            entry_id=1,
            summary='Shift: Worker A',
            start_datetime='2026-03-15T09:00:00+09:00',
            end_datetime='2026-03-15T17:00:00+09:00',
        )
        db_session.commit()

        assert task.task_type == 'sync_calendar_event'
        assert task.priority == 5


class TestNotificationAsync:
    """Test that notification functions enqueue tasks."""

    def test_notify_approval_requested_enqueues(self, app, db_session):
        from app.services.notification_service import notify_approval_requested
        result = notify_approval_requested(
            'owner@test.com', 'March 2026', 'Admin User',
        )
        assert result is True

        task = AsyncTask.query.filter_by(task_type='send_email').first()
        assert task is not None
        assert 'owner@test.com' in task.payload['to_email']
        assert '承認依頼' in task.payload['subject']

    def test_notify_approval_result_enqueues(self, app, db_session):
        from app.services.notification_service import notify_approval_result
        result = notify_approval_result(
            'admin@test.com', 'March 2026', 'approved',
        )
        assert result is True

        task = AsyncTask.query.filter_by(task_type='send_email').first()
        assert task is not None
        assert '承認' in task.payload['subject']


class TestCronEndpoint:
    """Tests for /api/cron/process-tasks."""

    def test_rejects_without_secret(self, client, db_session):
        db_session.commit()
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret'}):
            resp = client.post('/api/cron/process-tasks')
        assert resp.status_code == 401

    def test_accepts_with_valid_secret(self, client, db_session):
        db_session.commit()
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret'}):
            resp = client.post(
                '/api/cron/process-tasks',
                headers={'Authorization': 'Bearer test-secret'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'processed' in data

    def test_rejected_without_secret_in_non_debug(self, client, app, db_session):
        db_session.commit()
        # Without CRON_SECRET and not in debug mode, should reject
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CRON_SECRET', None)
            resp = client.post('/api/cron/process-tasks')
        # Non-debug test app rejects without secret
        assert resp.status_code == 401
