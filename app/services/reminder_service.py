"""Reminder service — submission deadline and pre-shift reminders.

Called by the cron endpoint to automatically send reminders, or
manually triggered by admin via API.
"""

from datetime import datetime, date, time, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.organization import Organization
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSchedule, ShiftScheduleEntry,
)
from app.models.reminder import Reminder
from app.models.user import User
from app.services.notification_service import notify_submission_deadline, notify_preshift

# Default settings
DEFAULT_DAYS_BEFORE_DEADLINE = 1
DEFAULT_TIME_DEADLINE = '09:00'
DEFAULT_DAYS_BEFORE_SHIFT = 1
DEFAULT_TIME_SHIFT = '21:00'


def _parse_time_str(t):
    """Parse 'HH:MM' string to a time object. Returns None on failure."""
    try:
        h, m = t.split(':')
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _get_reminder_trigger_dt(target_dt, days_before, time_str):
    """Calculate the exact datetime when a reminder should fire."""
    t = _parse_time_str(time_str) or time(9, 0)
    if isinstance(target_dt, datetime):
        target_date = target_dt.date()
    else:
        target_date = target_dt
    trigger_date = target_date - timedelta(days=days_before)
    return datetime.combine(trigger_date, t)


def check_and_send_submission_reminders():
    """Check all organizations and send submission deadline reminders.

    Called by the cron endpoint. For each org with open periods, checks
    if "now" has passed the trigger time (X days before deadline at HH:MM)
    and sends reminders to workers who haven't submitted.
    """
    orgs = Organization.query.filter_by(is_active=True).all()
    total_sent = 0
    total_skipped = 0
    now = datetime.utcnow()

    for org in orgs:
        days_before = org.get_setting('reminder_days_before_deadline', DEFAULT_DAYS_BEFORE_DEADLINE)
        time_str = org.get_setting('reminder_time_deadline', DEFAULT_TIME_DEADLINE)

        if days_before is None or days_before < 0:
            continue

        periods = ShiftPeriod.query.filter(
            ShiftPeriod.organization_id == org.id,
            ShiftPeriod.status == 'open',
            ShiftPeriod.submission_deadline.isnot(None),
            ShiftPeriod.submission_deadline > now,
        ).all()

        for period in periods:
            trigger_dt = _get_reminder_trigger_dt(
                period.submission_deadline, days_before, time_str
            )
            if now >= trigger_dt:
                sent, skipped = _send_submission_reminders_for_period(period, org)
                total_sent += sent
                total_skipped += skipped

    return {'sent': total_sent, 'skipped': total_skipped}


def send_submission_reminder_for_period(period_id, admin_user):
    """Manually send submission reminders for a specific period.

    Returns (result_dict, error_string).
    """
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return None, 'Period not found'

    org = db.session.get(Organization, period.organization_id)
    if not org:
        return None, 'Organization not found'

    sent, skipped = _send_submission_reminders_for_period(period, org)
    return {'sent': sent, 'skipped': skipped, 'period_id': period_id}, None


def _send_submission_reminders_for_period(period, org):
    """Internal: send reminders to workers who haven't submitted for a period."""
    sent = 0
    skipped = 0

    workers = User.query.filter_by(
        organization_id=org.id, role='worker', is_active=True
    ).all()

    submitted_user_ids = set(
        uid for (uid,) in db.session.query(ShiftSubmission.user_id).filter(
            ShiftSubmission.shift_period_id == period.id,
            ShiftSubmission.status.in_(['submitted', 'revised']),
        ).all()
    )

    deadline_str = period.submission_deadline.strftime('%Y年%m月%d日 %H:%M') if period.submission_deadline else ''
    base_url = current_app.config.get('BASE_URL', 'https://shifree.vercel.app')
    submit_url = f'{base_url}/worker'

    for worker in workers:
        if worker.id in submitted_user_ids:
            skipped += 1
            continue

        existing = Reminder.query.filter_by(
            reminder_type='submission_deadline',
            reference_id=period.id,
            user_id=worker.id,
        ).first()
        if existing:
            skipped += 1
            continue

        worker_name = worker.display_name or worker.email
        notify_submission_deadline(
            worker.email, worker_name, period.name, deadline_str, submit_url,
            organization_id=org.id,
        )

        reminder = Reminder(
            organization_id=org.id,
            reminder_type='submission_deadline',
            reference_id=period.id,
            user_id=worker.id,
        )
        db.session.add(reminder)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            skipped += 1
            continue
        sent += 1

    return sent, skipped


def check_and_send_preshift_reminders():
    """Check all organizations and send pre-shift reminders.

    For each org, finds confirmed schedule entries whose shift_date is
    X days from now, and the configured trigger time has passed.
    """
    orgs = Organization.query.filter_by(is_active=True).all()
    total_sent = 0
    total_skipped = 0
    now = datetime.utcnow()

    for org in orgs:
        days_before = org.get_setting('reminder_days_before_shift', DEFAULT_DAYS_BEFORE_SHIFT)
        time_str = org.get_setting('reminder_time_shift', DEFAULT_TIME_SHIFT)

        if days_before is None or days_before < 0:
            continue

        confirmed_schedules = db.session.query(ShiftSchedule.id).join(
            ShiftPeriod, ShiftSchedule.shift_period_id == ShiftPeriod.id
        ).filter(
            ShiftPeriod.organization_id == org.id,
            ShiftSchedule.status == 'confirmed',
        ).all()
        schedule_ids = [s.id for s in confirmed_schedules]

        if not schedule_ids:
            continue

        target_date = now.date() + timedelta(days=days_before)

        entries = ShiftScheduleEntry.query.filter(
            ShiftScheduleEntry.schedule_id.in_(schedule_ids),
            ShiftScheduleEntry.shift_date == target_date,
        ).all()

        trigger_dt = _get_reminder_trigger_dt(target_date, days_before, time_str)
        if now < trigger_dt:
            continue

        for entry in entries:
            existing = Reminder.query.filter_by(
                reminder_type='preshift',
                reference_id=entry.id,
                user_id=entry.user_id,
            ).first()
            if existing:
                total_skipped += 1
                continue

            worker = db.session.get(User, entry.user_id)
            if not worker:
                continue

            worker_name = worker.display_name or worker.email
            shift_date_str = entry.shift_date.strftime('%Y年%m月%d日')
            notify_preshift(
                worker.email, worker_name, shift_date_str,
                entry.start_time, entry.end_time,
                organization_id=org.id,
            )

            reminder = Reminder(
                organization_id=org.id,
                reminder_type='preshift',
                reference_id=entry.id,
                user_id=entry.user_id,
            )
            db.session.add(reminder)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                total_skipped += 1
                continue
            total_sent += 1

    return {'sent': total_sent, 'skipped': total_skipped}


def get_reminder_stats(period_id):
    """Get reminder stats for a period."""
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return None

    org = db.session.get(Organization, period.organization_id)
    if not org:
        return None

    total_workers = User.query.filter_by(
        organization_id=org.id, role='worker', is_active=True
    ).count()

    submitted_count = db.session.query(ShiftSubmission.id).filter(
        ShiftSubmission.shift_period_id == period_id,
        ShiftSubmission.status.in_(['submitted', 'revised']),
    ).count()

    reminders_sent = Reminder.query.filter_by(
        reminder_type='submission_deadline',
        reference_id=period_id,
    ).count()

    last_reminder = Reminder.query.filter_by(
        reminder_type='submission_deadline',
        reference_id=period_id,
    ).order_by(Reminder.sent_at.desc()).first()

    return {
        'total_workers': total_workers,
        'submitted_count': submitted_count,
        'unsubmitted_count': total_workers - submitted_count,
        'reminders_sent': reminders_sent,
        'last_sent_at': last_reminder.sent_at.isoformat() if last_reminder else None,
    }
