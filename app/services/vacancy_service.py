"""Vacancy service — find candidates, create requests, handle responses.

Manages the vacancy fill workflow: admin creates a request for an empty
shift slot, candidates are notified via email with accept/decline links,
and the first to accept fills the slot.
"""

import secrets
from datetime import datetime, date, timedelta

from flask import current_app

from app.extensions import db
from app.models.user import User
from app.models.shift import (
    ShiftScheduleEntry, ShiftSchedule, ShiftSubmission, ShiftSubmissionSlot,
)
from app.models.vacancy import VacancyRequest, VacancyCandidate, ShiftChangeLog
from app.services.notification_service import (
    notify_vacancy_request, notify_vacancy_accepted,
)
from app.services.audit_service import log_audit


def find_candidates(schedule_entry_id, organization_id):
    """Find available candidates for a vacancy based on submission data.

    1. Get the target entry's date/time
    2. Find workers who submitted availability for that date
    3. Exclude: original worker, already-assigned workers, inactive users
    4. Sort by weekly hours (ascending) for fairness
    """
    entry = db.session.get(ShiftScheduleEntry, schedule_entry_id)
    if not entry:
        return []

    schedule = db.session.get(ShiftSchedule, entry.schedule_id)
    if not schedule:
        return []

    shift_date = entry.shift_date

    available_slots = db.session.query(
        ShiftSubmissionSlot, ShiftSubmission
    ).join(
        ShiftSubmission, ShiftSubmissionSlot.submission_id == ShiftSubmission.id
    ).filter(
        ShiftSubmission.shift_period_id == schedule.shift_period_id,
        ShiftSubmissionSlot.slot_date == shift_date,
        ShiftSubmissionSlot.is_available == True,
    ).all()

    assigned_user_ids = set(
        row[0] for row in db.session.query(ShiftScheduleEntry.user_id).filter(
            ShiftScheduleEntry.schedule_id == schedule.id,
            ShiftScheduleEntry.shift_date == shift_date,
        ).all()
    )

    candidates = []
    for slot, submission in available_slots:
        user = db.session.get(User, submission.user_id)
        if not user or not user.is_active:
            continue
        if user.id == entry.user_id:
            continue
        if user.id in assigned_user_ids:
            continue

        candidates.append({
            'user_id': user.id,
            'user_name': user.display_name or user.email,
            'user_email': user.email,
            'start_time': slot.start_time,
            'end_time': slot.end_time,
            'weekly_hours': _calc_weekly_hours(user.id, schedule.id, shift_date),
        })

    candidates.sort(key=lambda c: c['weekly_hours'])
    return candidates


def _calc_weekly_hours(user_id, schedule_id, target_date):
    """Calculate total assigned hours for a user in the same week as target_date."""
    weekday = target_date.weekday()
    monday = target_date.toordinal() - weekday
    week_start = date.fromordinal(monday)
    week_end = week_start + timedelta(days=6)

    entries = ShiftScheduleEntry.query.filter(
        ShiftScheduleEntry.schedule_id == schedule_id,
        ShiftScheduleEntry.user_id == user_id,
        ShiftScheduleEntry.shift_date >= week_start,
        ShiftScheduleEntry.shift_date <= week_end,
    ).all()

    total_minutes = 0
    for e in entries:
        start_parts = e.start_time.split(':')
        end_parts = e.end_time.split(':')
        start_min = int(start_parts[0]) * 60 + int(start_parts[1])
        end_min = int(end_parts[0]) * 60 + int(end_parts[1])
        total_minutes += max(0, end_min - start_min)

    return round(total_minutes / 60, 1)


def create_vacancy_request(schedule_entry_id, reason, admin_user):
    """Create a new vacancy request in 'open' status.

    Returns (vacancy, error_string).
    """
    entry = db.session.get(ShiftScheduleEntry, schedule_entry_id)
    if not entry:
        return None, 'シフト枠が見つかりません'

    existing = VacancyRequest.query.filter(
        VacancyRequest.schedule_entry_id == schedule_entry_id,
        VacancyRequest.status.in_(['open', 'notified']),
    ).first()
    if existing:
        return None, 'このシフト枠にはすでに補充リクエストがあります'

    vacancy = VacancyRequest(
        schedule_entry_id=schedule_entry_id,
        original_user_id=entry.user_id,
        reason=reason,
        status='open',
        created_by=admin_user.id,
    )
    db.session.add(vacancy)

    log_audit(
        action='VACANCY_CREATED',
        resource_type='VacancyRequest',
        resource_id=None,
        actor_id=admin_user.id,
        organization_id=admin_user.organization_id,
        new_values={
            'schedule_entry_id': schedule_entry_id,
            'reason': reason,
        },
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, 'データベースエラー'

    return vacancy, None


def send_vacancy_notifications(vacancy_request_id, candidate_user_ids, base_url):
    """Send notification emails to selected candidates.

    Returns (result_dict, error_string).
    """
    vacancy = db.session.get(VacancyRequest, vacancy_request_id)
    if not vacancy:
        return None, 'リクエストが見つかりません'
    if vacancy.status not in ('open', 'notified'):
        return None, f'現在のステータス ({vacancy.status}) では通知を送信できません'

    entry = vacancy.schedule_entry
    notified_count = 0

    for user_id in candidate_user_ids:
        user = db.session.get(User, user_id)
        if not user or not user.is_active:
            continue

        existing = VacancyCandidate.query.filter_by(
            vacancy_request_id=vacancy_request_id,
            user_id=user_id,
        ).first()
        if existing:
            continue

        token = secrets.token_urlsafe(32)
        candidate = VacancyCandidate(
            vacancy_request_id=vacancy_request_id,
            user_id=user_id,
            status='notified',
            response_token=token,
            notified_at=datetime.utcnow(),
        )
        db.session.add(candidate)

        accept_url = f"{base_url}/vacancy/respond?token={token}&action=accept"
        decline_url = f"{base_url}/vacancy/respond?token={token}&action=decline"
        try:
            notify_vacancy_request(
                to_email=user.email,
                user_name=user.display_name or user.email,
                shift_date=entry.shift_date.isoformat(),
                start_time=entry.start_time,
                end_time=entry.end_time,
                reason=vacancy.reason or '',
                accept_url=accept_url,
                decline_url=decline_url,
                organization_id=vacancy.original_user.organization_id if vacancy.original_user else None,
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send vacancy notification to {user.email}: {e}")

        notified_count += 1

    vacancy.status = 'notified'
    vacancy.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, 'データベースエラー'

    return {'notified_count': notified_count}, None


def respond_to_vacancy(token, action):
    """Handle a candidate's response to a vacancy request.

    Returns (result_dict, error_string).
    result_dict has 'status' key: 'accepted', 'declined', 'already_filled', 'invalid', 'expired'
    """
    candidate = VacancyCandidate.query.filter_by(response_token=token).first()
    if not candidate:
        return {'status': 'invalid'}, None

    vacancy = candidate.vacancy_request
    if not vacancy:
        return {'status': 'invalid'}, None

    # Already responded
    if candidate.status in ('accepted', 'declined', 'expired'):
        if candidate.status == 'accepted':
            return {'status': 'already_accepted'}, None
        if vacancy.status == 'accepted':
            return {'status': 'already_filled'}, None
        return {'status': 'expired'}, None

    # Vacancy no longer active
    if vacancy.status not in ('notified',):
        return {'status': 'already_filled' if vacancy.status == 'accepted' else 'expired'}, None

    if action == 'decline':
        candidate.status = 'declined'
        candidate.responded_at = datetime.utcnow()

        remaining = VacancyCandidate.query.filter(
            VacancyCandidate.vacancy_request_id == vacancy.id,
            VacancyCandidate.status == 'notified',
        ).count()
        if remaining == 0:
            vacancy.status = 'expired'
            vacancy.updated_at = datetime.utcnow()

        db.session.commit()
        return {'status': 'declined'}, None

    if action == 'accept':
        # Race condition guard
        if vacancy.status != 'notified':
            return {'status': 'already_filled'}, None

        candidate.status = 'accepted'
        candidate.responded_at = datetime.utcnow()

        vacancy.status = 'accepted'
        vacancy.accepted_by = candidate.user_id
        vacancy.accepted_at = datetime.utcnow()
        vacancy.updated_at = datetime.utcnow()

        entry = vacancy.schedule_entry
        old_user_id = entry.user_id
        entry.user_id = candidate.user_id
        entry.updated_at = datetime.utcnow()

        change_log = ShiftChangeLog(
            schedule_entry_id=entry.id,
            vacancy_request_id=vacancy.id,
            change_type='vacancy_fill',
            original_user_id=old_user_id,
            new_user_id=candidate.user_id,
            reason=vacancy.reason,
            performed_by=vacancy.created_by,
        )
        db.session.add(change_log)

        log_audit(
            action='VACANCY_ACCEPTED',
            resource_type='VacancyRequest',
            resource_id=vacancy.id,
            actor_id=candidate.user_id,
            organization_id=vacancy.original_user.organization_id if vacancy.original_user else None,
            old_values={'user_id': old_user_id},
            new_values={'user_id': candidate.user_id},
        )

        # Expire other candidates
        other_candidates = VacancyCandidate.query.filter(
            VacancyCandidate.vacancy_request_id == vacancy.id,
            VacancyCandidate.id != candidate.id,
            VacancyCandidate.status.in_(['pending', 'notified']),
        ).all()
        for c in other_candidates:
            c.status = 'expired'

        # Google Calendar sync (best-effort)
        _sync_calendar_on_accept(vacancy, entry, old_user_id, candidate.user_id)

        # Notify admin
        try:
            admin = db.session.get(User, vacancy.created_by)
            new_user = db.session.get(User, candidate.user_id)
            original_user = db.session.get(User, old_user_id)
            if admin:
                notify_vacancy_accepted(
                    admin_email=admin.email,
                    shift_date=entry.shift_date.isoformat(),
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    original_name=original_user.display_name if original_user else '不明',
                    new_name=new_user.display_name if new_user else '不明',
                    organization_id=admin.organization_id,
                )
        except Exception as e:
            current_app.logger.error(f"Failed to send vacancy accepted notification: {e}")

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return None, 'データベースエラー'

        return {'status': 'accepted'}, None

    return {'status': 'invalid'}, None


def _sync_calendar_on_accept(vacancy, entry, old_user_id, new_user_id):
    """Best-effort Google Calendar sync when a vacancy is accepted."""
    try:
        from app.services.auth_service import get_credentials_for_user
        from app.services.calendar_service import delete_event, create_event

        admin = db.session.get(User, vacancy.created_by)
        if not admin:
            return

        credentials = get_credentials_for_user(admin)
        if not credentials:
            return

        if entry.calendar_event_id:
            old_user = db.session.get(User, old_user_id)
            if old_user:
                try:
                    delete_event(credentials, old_user.email, entry.calendar_event_id)
                except Exception as e:
                    current_app.logger.warning(f"Failed to delete old calendar event: {e}")

        new_user = db.session.get(User, new_user_id)
        if new_user:
            summary = f"シフト: {new_user.display_name or new_user.email}"
            start_dt = f"{entry.shift_date.isoformat()}T{entry.start_time}:00"
            end_dt = f"{entry.shift_date.isoformat()}T{entry.end_time}:00"
            try:
                event_id = create_event(
                    credentials, new_user.email, summary, start_dt, end_dt,
                    description="シフリーにより自動作成（欠員補充）"
                )
                entry.calendar_event_id = event_id
                entry.synced_at = datetime.utcnow()
            except Exception as e:
                current_app.logger.warning(f"Failed to create new calendar event: {e}")
    except Exception as e:
        current_app.logger.error(f"Calendar sync error during vacancy accept: {e}")


def cancel_vacancy_request(vacancy_request_id, admin_user):
    """Cancel a vacancy request and expire all candidates.

    Returns (vacancy, error_string).
    """
    vacancy = db.session.get(VacancyRequest, vacancy_request_id)
    if not vacancy:
        return None, 'リクエストが見つかりません'
    if vacancy.status in ('accepted', 'cancelled'):
        return None, f'このリクエストは既に{vacancy.status}です'

    vacancy.status = 'cancelled'
    vacancy.updated_at = datetime.utcnow()

    candidates = VacancyCandidate.query.filter(
        VacancyCandidate.vacancy_request_id == vacancy.id,
        VacancyCandidate.status.in_(['pending', 'notified']),
    ).all()
    for c in candidates:
        c.status = 'expired'

    log_audit(
        action='VACANCY_CANCELLED',
        resource_type='VacancyRequest',
        resource_id=vacancy.id,
        actor_id=admin_user.id,
        organization_id=admin_user.organization_id,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, 'データベースエラー'

    return vacancy, None
