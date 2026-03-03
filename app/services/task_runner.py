"""Task runner service — processes pending AsyncTasks.

Called by the cron endpoint to drain the queue.  Each task_type maps
to a handler function.  Failed handlers trigger retry with exponential
backoff.
"""

import logging
from datetime import datetime

from app.extensions import db
from app.models.async_task import AsyncTask

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {}


def register_handler(task_type):
    """Decorator to register a handler for a task type."""
    def decorator(fn):
        _HANDLERS[task_type] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------

@register_handler('send_email')
def _handle_send_email(payload):
    from app.services.notification_service import send_email
    success = send_email(
        to_email=payload['to_email'],
        subject=payload['subject'],
        body_html=payload['body_html'],
    )
    if not success:
        raise RuntimeError("Email send failed (SMTP error or not configured)")


@register_handler('sync_calendar_event')
def _handle_sync_calendar_event(payload):
    from app.services.calendar_service import create_event
    from app.services.auth_service import get_credentials_for_user
    from app.models.shift import ShiftScheduleEntry
    from app.models.user import User

    user_id = payload['user_id']
    entry_id = payload['entry_id']
    user = db.session.get(User, user_id)
    if not user:
        raise RuntimeError(f"User {user_id} not found")
    credentials = get_credentials_for_user(user)
    if not credentials:
        raise RuntimeError(f"No Google credentials for user {user_id}")

    entry = db.session.get(ShiftScheduleEntry, entry_id)
    if not entry:
        logger.warning("ShiftScheduleEntry %s not found, skipping", entry_id)
        return  # nothing to do — task considered successful

    result = create_event(
        credentials=credentials,
        calendar_id=payload.get('calendar_id', 'primary'),
        summary=payload['summary'],
        start_datetime=payload['start_datetime'],
        end_datetime=payload['end_datetime'],
        description=payload.get('description'),
    )

    # Update entry with calendar event reference
    if result and 'id' in result:
        entry.calendar_event_id = result['id']
        entry.synced_at = datetime.utcnow()
        db.session.commit()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def process_pending_tasks(batch_size=20):
    """Process up to *batch_size* pending tasks.

    Returns a summary dict with counts of processed/succeeded/failed tasks.
    """
    now = datetime.utcnow()
    tasks = (
        AsyncTask.query
        .filter(AsyncTask.status == 'pending', AsyncTask.next_run_at <= now)
        .order_by(AsyncTask.priority.desc(), AsyncTask.created_at.asc())
        .limit(batch_size)
        .all()
    )

    stats = {'processed': 0, 'succeeded': 0, 'failed': 0, 'dead': 0}

    for task in tasks:
        handler = _HANDLERS.get(task.task_type)
        if handler is None:
            logger.error("No handler for task type %r (task %s)", task.task_type, task.id)
            task.mark_failed(f"Unknown task type: {task.task_type}")
            task.status = 'dead'  # no point retrying
            db.session.commit()
            stats['processed'] += 1
            stats['dead'] += 1
            continue

        task.mark_running()
        db.session.commit()
        stats['processed'] += 1

        try:
            handler(task.payload)
            task.mark_completed()
            db.session.commit()
            stats['succeeded'] += 1
            logger.info("Task %s (%s) completed", task.id, task.task_type)
        except Exception as exc:
            db.session.rollback()
            # Re-fetch after rollback
            task = db.session.get(AsyncTask, task.id)
            task.mark_failed(str(exc))
            db.session.commit()
            if task.status == 'dead':
                stats['dead'] += 1
                logger.error("Task %s (%s) dead after %d retries: %s",
                             task.id, task.task_type, task.max_retries, exc)
            else:
                stats['failed'] += 1
                logger.warning("Task %s (%s) failed (retry %d/%d): %s",
                               task.id, task.task_type, task.retry_count,
                               task.max_retries, exc)

    return stats


# ---------------------------------------------------------------------------
# Task creation helpers
# ---------------------------------------------------------------------------

def enqueue_email(to_email, subject, body_html, *, organization_id=None, created_by=None, priority=0):
    """Enqueue an email for async delivery."""
    task = AsyncTask(
        task_type='send_email',
        payload={
            'to_email': to_email,
            'subject': subject,
            'body_html': body_html,
        },
        organization_id=organization_id,
        created_by=created_by,
        priority=priority,
    )
    db.session.add(task)
    db.session.flush()
    return task


def enqueue_calendar_sync(user_id, entry_id, summary, start_datetime, end_datetime, *,
                          calendar_id='primary', description=None,
                          organization_id=None, created_by=None):
    """Enqueue a Google Calendar event creation."""
    task = AsyncTask(
        task_type='sync_calendar_event',
        payload={
            'user_id': user_id,
            'entry_id': entry_id,
            'calendar_id': calendar_id,
            'summary': summary,
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'description': description,
        },
        organization_id=organization_id,
        created_by=created_by,
        priority=5,  # calendar sync is higher priority
    )
    db.session.add(task)
    db.session.flush()
    return task
