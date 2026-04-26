import logging
from datetime import datetime, date, timedelta
from app.extensions import db
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.opening_hours import OpeningHours, OpeningHoursException
from app.models.user import User
from app.utils.validators import validate_time_str, validate_text_length

logger = logging.getLogger(__name__)


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


def get_period_impact_summary(period):
    """期間削除前の影響範囲を集計する（UI 確認ダイアログ用）。"""
    from app.models.reminder import Reminder
    from app.models.vacancy import VacancyRequest, ShiftChangeLog

    submissions_count = period.submissions.count()
    entries = []
    synced_entries = 0
    for sch in period.schedules.all():
        for e in sch.entries.all():
            entries.append(e)
            if e.calendar_event_id:
                synced_entries += 1

    entry_ids = [e.id for e in entries]
    vacancies_count = 0
    change_logs_count = 0
    reminders_count = 0
    if entry_ids:
        vacancies_count = VacancyRequest.query.filter(
            VacancyRequest.schedule_entry_id.in_(entry_ids),
        ).count()
        change_logs_count = ShiftChangeLog.query.filter(
            ShiftChangeLog.schedule_entry_id.in_(entry_ids),
        ).count()
        reminders_count += Reminder.query.filter(
            Reminder.reminder_type == 'preshift',
            Reminder.reference_id.in_(entry_ids),
        ).count()
    reminders_count += Reminder.query.filter(
        Reminder.reminder_type == 'submission_deadline',
        Reminder.reference_id == period.id,
    ).count()

    return {
        'submissions': submissions_count,
        'entries': len(entries),
        'synced_entries': synced_entries,
        'vacancies': vacancies_count,
        'change_logs': change_logs_count,
        'reminders': reminders_count,
    }


def delete_period_with_cleanup(period):
    """シフト期間と関連データを完全削除する。

    SQLAlchemy の cascade に乗らない以下を手動で削除する:
      - Reminder（loose FK: reference_id が period.id または entry.id）
      - VacancyRequest / VacancyCandidate（schedule_entry_id 経由）
      - ShiftChangeLog（schedule_entry_id 経由）
      - Google Calendar event（best-effort、worker 認証情報が無ければスキップ）

    cascade で削除されるもの:
      - ShiftSubmission, ShiftSubmissionSlot
      - ShiftSchedule, ShiftScheduleEntry, ApprovalHistory

    呼び出し元はこの関数の後に db.session.commit() する責務を持つ。
    Google Calendar の削除失敗は DB 削除を妨げない。

    Returns:
        dict: 削除した件数のサマリ
    """
    from app.models.reminder import Reminder
    from app.models.vacancy import VacancyRequest, ShiftChangeLog
    from app.services.calendar_service import delete_event
    from app.services.auth_service import (
        get_credentials_for_user, CredentialsExpiredError,
    )

    submissions_count = period.submissions.count()

    # 全 schedule の entry を集約
    entries = []
    for sch in period.schedules.all():
        entries.extend(sch.entries.all())
    entry_ids = [e.id for e in entries]

    # Google Calendar event の best-effort 削除
    # skipped: credentials 無し・worker 無しで実行できなかった件数
    # failed:  実際に API を呼んだが例外で失敗した件数
    calendar_deleted = 0
    calendar_skipped = 0
    calendar_failed = 0
    credentials_cache = {}
    for entry in entries:
        if not entry.calendar_event_id:
            continue
        worker = entry.user
        if not worker:
            calendar_skipped += 1
            continue
        if worker.id not in credentials_cache:
            try:
                credentials_cache[worker.id] = get_credentials_for_user(worker)
            except CredentialsExpiredError:
                credentials_cache[worker.id] = None
            except Exception as e:
                logger.warning("Failed to load credentials for user %s: %s", worker.id, e)
                credentials_cache[worker.id] = None
        cred = credentials_cache[worker.id]
        if cred is None:
            calendar_skipped += 1
            continue
        try:
            delete_event(cred, 'primary', entry.calendar_event_id)
            calendar_deleted += 1
        except Exception as e:
            logger.warning(
                "Failed to delete calendar event %s for entry %s: %s",
                entry.calendar_event_id, entry.id, e,
            )
            calendar_failed += 1

    # Reminder クリーンアップ（loose FK）
    reminders_count = 0
    if entry_ids:
        reminders_count += Reminder.query.filter(
            Reminder.reminder_type == 'preshift',
            Reminder.reference_id.in_(entry_ids),
        ).delete(synchronize_session=False)
    reminders_count += Reminder.query.filter(
        Reminder.reminder_type == 'submission_deadline',
        Reminder.reference_id == period.id,
    ).delete(synchronize_session=False)

    # ShiftChangeLog → VacancyRequest の順で削除（FK 順守）
    change_logs_count = 0
    vacancies_count = 0
    if entry_ids:
        change_logs_count = ShiftChangeLog.query.filter(
            ShiftChangeLog.schedule_entry_id.in_(entry_ids),
        ).delete(synchronize_session=False)
        for vr in VacancyRequest.query.filter(
            VacancyRequest.schedule_entry_id.in_(entry_ids),
        ).all():
            db.session.delete(vr)  # candidates は cascade で削除
            vacancies_count += 1

    # Period 本体を削除（submissions / schedules / entries / history は cascade）
    db.session.delete(period)

    return {
        'submissions': submissions_count,
        'entries': len(entries),
        'reminders': reminders_count,
        'vacancies': vacancies_count,
        'change_logs': change_logs_count,
        'calendar_events_deleted': calendar_deleted,
        'calendar_events_skipped': calendar_skipped,
        'calendar_events_failed': calendar_failed,
    }
