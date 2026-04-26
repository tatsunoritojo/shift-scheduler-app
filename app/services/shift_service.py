from datetime import datetime, date, timedelta
from app.extensions import db
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.opening_hours import OpeningHours, OpeningHoursException
from app.models.user import User
from app.utils.validators import validate_time_str, validate_text_length


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
    # Validate text lengths
    validate_text_length(notes, 'notes', 5000)

    # Load period for date range validation
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        raise ValueError(f"Period {period_id} not found")

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
        try:
            slot_date = date.fromisoformat(slot['slot_date'])
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"Invalid slot_date: {slot.get('slot_date')}")

        # Validate slot_date is within period range
        if slot_date < period.start_date or slot_date > period.end_date:
            raise ValueError(
                f"slot_date {slot_date.isoformat()} is outside period range "
                f"({period.start_date.isoformat()} - {period.end_date.isoformat()})"
            )

        # Validate time strings if provided
        start_time = slot.get('start_time')
        end_time = slot.get('end_time')
        if start_time:
            validate_time_str(start_time, 'start_time')
        if end_time:
            validate_time_str(end_time, 'end_time')

        auto_start = slot.get('auto_calculated_start')
        auto_end = slot.get('auto_calculated_end')
        if auto_start:
            validate_time_str(auto_start, 'auto_calculated_start')
        if auto_end:
            validate_time_str(auto_end, 'auto_calculated_end')

        s = ShiftSubmissionSlot(
            submission_id=submission.id,
            slot_date=slot_date,
            is_available=slot.get('is_available', False),
            start_time=start_time,
            end_time=end_time,
            is_custom_time=slot.get('is_custom_time', False),
            auto_calculated_start=auto_start,
            auto_calculated_end=auto_end,
            notes=slot.get('notes'),
        )
        db.session.add(s)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
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


def save_schedule(period_id, created_by, entries_data, organization_id=None):
    """Create or update a shift schedule."""
    # Check for duplicate: reject if non-draft, non-rejected schedule exists for this period
    existing = ShiftSchedule.query.filter(
        ShiftSchedule.shift_period_id == period_id,
        ShiftSchedule.status.notin_(['draft', 'rejected']),
    ).first()
    if existing:
        raise ValueError(
            f"A schedule with status '{existing.status}' already exists for this period. "
            "Cannot create a new schedule."
        )

    # Load period for date range validation
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        raise ValueError(f"Period {period_id} not found")

    # Validate all entry user_ids if organization_id is provided
    if organization_id and entries_data:
        user_ids = list({entry['user_id'] for entry in entries_data})
        valid_users = User.query.filter(
            User.id.in_(user_ids),
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.role == 'worker',
        ).all()
        valid_user_ids = {u.id for u in valid_users}
        invalid_ids = set(user_ids) - valid_user_ids
        if invalid_ids:
            raise ValueError(
                f"Invalid user_ids: {sorted(invalid_ids)}. "
                "Users must exist, belong to this organization, be active, and have worker role."
            )

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
        try:
            shift_date = date.fromisoformat(entry['shift_date'])
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"Invalid shift_date: {entry.get('shift_date')}")

        # Validate shift_date is within period range
        if shift_date < period.start_date or shift_date > period.end_date:
            raise ValueError(
                f"shift_date {shift_date.isoformat()} is outside period range "
                f"({period.start_date.isoformat()} - {period.end_date.isoformat()})"
            )

        # Validate time strings
        validate_time_str(entry['start_time'], 'start_time')
        validate_time_str(entry['end_time'], 'end_time')

        e = ShiftScheduleEntry(
            schedule_id=schedule.id,
            user_id=entry['user_id'],
            shift_date=shift_date,
            start_time=entry['start_time'],
            end_time=entry['end_time'],
        )
        db.session.add(e)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
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
