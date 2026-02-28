from datetime import datetime, date, timedelta
from app.extensions import db
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.opening_hours import OpeningHours, OpeningHoursException


def get_opening_hours_for_date(org_id, target_date):
    """Get effective opening hours for a specific date, considering exceptions."""
    exc = OpeningHoursException.query.filter_by(
        organization_id=org_id, exception_date=target_date
    ).first()

    if exc:
        if exc.is_closed:
            return None  # Closed
        return {'start_time': exc.start_time, 'end_time': exc.end_time}

    dow = target_date.weekday()
    # Convert Python weekday (Mon=0) to our schema (Sun=0)
    dow_schema = (dow + 1) % 7

    oh = OpeningHours.query.filter_by(
        organization_id=org_id, day_of_week=dow_schema
    ).first()

    if not oh or oh.is_closed:
        return None
    return {'start_time': oh.start_time, 'end_time': oh.end_time}


def get_opening_hours_for_period(org_id, start_date, end_date):
    """Get opening hours for every date in a period."""
    result = {}
    current = start_date
    while current <= end_date:
        hours = get_opening_hours_for_date(org_id, current)
        result[current.isoformat()] = hours
        current += timedelta(days=1)
    return result


def create_or_update_submission(period_id, user_id, slots_data, notes=None):
    """Create or update a shift submission with slots."""
    submission = ShiftSubmission.query.filter_by(
        shift_period_id=period_id, user_id=user_id
    ).first()

    if not submission:
        submission = ShiftSubmission(
            shift_period_id=period_id,
            user_id=user_id,
            status='submitted',
            submitted_at=datetime.utcnow(),
            notes=notes,
        )
        db.session.add(submission)
        db.session.flush()
    else:
        submission.status = 'submitted'
        submission.submitted_at = datetime.utcnow()
        submission.notes = notes
        # Delete existing slots
        ShiftSubmissionSlot.query.filter_by(submission_id=submission.id).delete()

    for slot in slots_data:
        s = ShiftSubmissionSlot(
            submission_id=submission.id,
            slot_date=date.fromisoformat(slot['slot_date']),
            is_available=slot.get('is_available', False),
            start_time=slot.get('start_time'),
            end_time=slot.get('end_time'),
            is_custom_time=slot.get('is_custom_time', False),
            auto_calculated_start=slot.get('auto_calculated_start'),
            auto_calculated_end=slot.get('auto_calculated_end'),
            notes=slot.get('notes'),
        )
        db.session.add(s)

    db.session.commit()
    return submission


def get_submissions_for_period(period_id):
    """Get all submissions for a shift period with their slots."""
    submissions = ShiftSubmission.query.filter_by(shift_period_id=period_id).all()
    result = []
    for sub in submissions:
        data = sub.to_dict()
        data['slots'] = [s.to_dict() for s in sub.slots.all()]
        result.append(data)
    return result


def save_schedule(period_id, created_by, entries_data):
    """Create or update a shift schedule."""
    schedule = ShiftSchedule.query.filter_by(
        shift_period_id=period_id, status='draft'
    ).first()

    if not schedule:
        schedule = ShiftSchedule(
            shift_period_id=period_id,
            created_by=created_by,
            status='draft',
        )
        db.session.add(schedule)
        db.session.flush()
    else:
        ShiftScheduleEntry.query.filter_by(schedule_id=schedule.id).delete()

    for entry in entries_data:
        e = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=entry['user_id'],
            shift_date=date.fromisoformat(entry['shift_date']),
            start_time=entry['start_time'],
            end_time=entry['end_time'],
        )
        db.session.add(e)

    db.session.commit()
    return schedule


def get_worker_hours_summary(schedule_id):
    """Calculate total hours per worker for a schedule."""
    entries = ShiftScheduleEntry.query.filter_by(schedule_id=schedule_id).all()
    summary = {}
    for entry in entries:
        uid = entry.user_id
        if uid not in summary:
            summary[uid] = {
                'user_id': uid,
                'user_name': entry.user.display_name if entry.user else None,
                'total_hours': 0,
                'shift_count': 0,
            }
        start_mins = int(entry.start_time.split(':')[0]) * 60 + int(entry.start_time.split(':')[1])
        end_mins = int(entry.end_time.split(':')[0]) * 60 + int(entry.end_time.split(':')[1])
        summary[uid]['total_hours'] += (end_mins - start_mins) / 60
        summary[uid]['shift_count'] += 1
    return list(summary.values())
