import secrets

from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime, timedelta

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_role, get_current_user
from app.models.organization import Organization
from app.models.opening_hours import OpeningHours, OpeningHoursException, SyncOperationLog
from app.models.shift import ShiftPeriod, ShiftSchedule, ShiftScheduleEntry
from app.models.user import User
from app.services.shift_service import (
    get_submissions_for_period, save_schedule, get_worker_hours_summary,
    get_opening_hours_for_period,
)
from app.services.approval_service import submit_for_approval, confirm_schedule
from app.services.auth_service import get_credentials_for_user, CredentialsExpiredError
from app.services.calendar_service import create_event
from app.services.opening_hours_sync_service import (
    export_opening_hours_to_calendar,
    import_opening_hours_from_calendar,
)
from app.utils.validators import validate_time_str, validate_text_length
from app.utils.errors import error_response
from app.models.membership import OrganizationMember, InvitationToken
from app.services.audit_service import log_audit

api_admin_bp = Blueprint('api_admin', __name__, url_prefix='/api/admin')


def _get_or_create_org(user):
    """Get user's organization or create a new one for the user."""
    if user.organization_id:
        return db.session.get(Organization, user.organization_id)
    # Create a new org for this user instead of assigning to an arbitrary existing one
    org = Organization(name=f'{user.display_name or user.email} の組織', admin_email=user.email, owner_email=user.email)
    db.session.add(org)
    db.session.flush()
    user.organization_id = org.id
    # Initialize default opening hours (Mon-Sun 09:00-21:00)
    OpeningHours.create_defaults(org.id)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return org


# --- Opening Hours ---

@api_admin_bp.route('/opening-hours', methods=['GET'])
@require_role('admin')
def get_opening_hours():
    user = get_current_user()
    org = _get_or_create_org(user)
    hours = OpeningHours.query.filter_by(organization_id=org.id).order_by(OpeningHours.day_of_week).all()
    return jsonify([h.to_dict() for h in hours])


@api_admin_bp.route('/opening-hours', methods=['PUT'])
@require_role('admin')
def update_opening_hours():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)

    if not data or not isinstance(data, list):
        return error_response("Expected array of opening hours", 400)

    for item in data:
        dow = item.get('day_of_week')
        if not isinstance(dow, int) or dow < 0 or dow > 6:
            return error_response("day_of_week must be an integer between 0 and 6", 400, code="VALIDATION_ERROR")

        # Validate time strings
        start_time = item.get('start_time', '09:00')
        end_time = item.get('end_time', '21:00')
        try:
            validate_time_str(start_time, 'start_time')
            validate_time_str(end_time, 'end_time')
        except ValueError as e:
            return error_response(str(e), 400, code="VALIDATION_ERROR")

        existing = OpeningHours.query.filter_by(
            organization_id=org.id, day_of_week=dow
        ).first()

        if existing:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.is_closed = item.get('is_closed', False)
        else:
            oh = OpeningHours(
                organization_id=org.id,
                day_of_week=dow,
                start_time=start_time,
                end_time=end_time,
                is_closed=item.get('is_closed', False),
            )
            db.session.add(oh)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    hours = OpeningHours.query.filter_by(organization_id=org.id).order_by(OpeningHours.day_of_week).all()
    return jsonify([h.to_dict() for h in hours])


# --- Opening Hours Exceptions ---

@api_admin_bp.route('/opening-hours/exceptions', methods=['GET'])
@require_role('admin')
def get_exceptions():
    user = get_current_user()
    org = _get_or_create_org(user)
    exceptions = OpeningHoursException.query.filter_by(
        organization_id=org.id
    ).order_by(OpeningHoursException.exception_date).all()
    return jsonify([e.to_dict() for e in exceptions])


@api_admin_bp.route('/opening-hours/exceptions', methods=['POST'])
@require_role('admin')
def create_exception():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)

    if not data or not data.get('exception_date'):
        return error_response("exception_date is required", 400)

    from app.utils.validators import parse_date
    exc_date = parse_date(data['exception_date'])
    if not exc_date:
        return error_response("Invalid date format", 400)

    source = data.get('source', 'manual')
    if source not in ('manual', 'calendar'):
        return error_response("Invalid source. Allowed: manual, calendar", 400)

    # Validate time strings if provided
    exc_start_time = data.get('start_time')
    exc_end_time = data.get('end_time')
    try:
        if exc_start_time:
            validate_time_str(exc_start_time, 'start_time')
        if exc_end_time:
            validate_time_str(exc_end_time, 'end_time')
        validate_text_length(data.get('reason'), 'reason', 2000)
    except ValueError as e:
        return error_response(str(e), 400, code="VALIDATION_ERROR")

    exc = OpeningHoursException(
        organization_id=org.id,
        exception_date=exc_date,
        start_time=exc_start_time,
        end_time=exc_end_time,
        is_closed=data.get('is_closed', False),
        reason=data.get('reason'),
        source=source,
    )
    db.session.add(exc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify(exc.to_dict()), 201


@api_admin_bp.route('/opening-hours/exceptions/<int:exc_id>', methods=['PUT'])
@require_role('admin')
def update_exception(exc_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    exc = db.session.get(OpeningHoursException, exc_id)
    if not exc or exc.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")
    try:
        if data.get('start_time') is not None:
            validate_time_str(data['start_time'], 'start_time')
            exc.start_time = data['start_time']
        if data.get('end_time') is not None:
            validate_time_str(data['end_time'], 'end_time')
            exc.end_time = data['end_time']
        if 'reason' in data:
            validate_text_length(data['reason'], 'reason', 2000)
    except ValueError as e:
        return error_response(str(e), 400, code="VALIDATION_ERROR")
    if 'is_closed' in data:
        exc.is_closed = data['is_closed']
    if 'reason' in data:
        exc.reason = data['reason']
    exc.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify(exc.to_dict())


@api_admin_bp.route('/opening-hours/exceptions/<int:exc_id>', methods=['DELETE'])
@require_role('admin')
def delete_exception(exc_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    exc = db.session.get(OpeningHoursException, exc_id)
    if not exc or exc.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    db.session.delete(exc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return '', 204


# --- Opening Hours Calendar Sync ---

@api_admin_bp.route('/opening-hours/sync/export', methods=['POST'])
@require_role('admin')
def sync_export_opening_hours():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)

    if not data or not data.get('start_date') or not data.get('end_date'):
        return error_response("start_date and end_date are required", 400)

    from app.utils.validators import parse_date
    start = parse_date(data['start_date'])
    end = parse_date(data['end_date'])
    if not start or not end:
        return error_response("Invalid date format (YYYY-MM-DD)", 400)
    if (end - start).days > 90:
        return error_response("日付範囲は最大90日までです", 400)

    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except Exception as e:
        current_app.logger.error(f"Credential error: {e}")
        return error_response("認証エラーが発生しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("Google認証情報がありません。再ログインしてください。", 401, code="AUTH_REQUIRED")

    result = export_opening_hours_to_calendar(org.id, credentials, start, end)
    return jsonify(result)


@api_admin_bp.route('/opening-hours/sync/import', methods=['POST'])
@require_role('admin')
def sync_import_opening_hours():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)

    if not data or not data.get('start_date') or not data.get('end_date'):
        return error_response("start_date and end_date are required", 400)

    from app.utils.validators import parse_date
    start = parse_date(data['start_date'])
    end = parse_date(data['end_date'])
    if not start or not end:
        return error_response("Invalid date format (YYYY-MM-DD)", 400)
    if (end - start).days > 90:
        return error_response("日付範囲は最大90日までです", 400)

    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except Exception as e:
        current_app.logger.error(f"Credential error: {e}")
        return error_response("認証エラーが発生しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("Google認証情報がありません。再ログインしてください。", 401, code="AUTH_REQUIRED")

    result = import_opening_hours_from_calendar(org.id, credentials, start, end)
    return jsonify(result)


# --- Sync Status & Logs ---

@api_admin_bp.route('/opening-hours/sync/status', methods=['GET'])
@require_role('admin')
def get_sync_status():
    user = get_current_user()
    org = _get_or_create_org(user)

    last_log = SyncOperationLog.query.filter_by(
        organization_id=org.id
    ).order_by(SyncOperationLog.performed_at.desc()).first()

    from sqlalchemy import func
    cal_stats = db.session.query(
        func.count(OpeningHoursException.id),
        func.min(OpeningHoursException.exception_date),
        func.max(OpeningHoursException.exception_date),
    ).filter(
        OpeningHoursException.organization_id == org.id,
        OpeningHoursException.source == 'calendar',
    ).first()

    result = {
        'last_sync': last_log.to_dict() if last_log else None,
        'calendar_exceptions': {
            'count': cal_stats[0] if cal_stats else 0,
            'min_date': cal_stats[1].isoformat() if cal_stats and cal_stats[1] else None,
            'max_date': cal_stats[2].isoformat() if cal_stats and cal_stats[2] else None,
        },
    }
    return jsonify(result)


@api_admin_bp.route('/opening-hours/sync/logs', methods=['GET'])
@require_role('admin')
def get_sync_logs():
    user = get_current_user()
    org = _get_or_create_org(user)

    logs = SyncOperationLog.query.filter_by(
        organization_id=org.id
    ).order_by(SyncOperationLog.performed_at.desc()).limit(20).all()

    return jsonify([log.to_dict() for log in logs])


# --- Shift Periods ---

@api_admin_bp.route('/periods', methods=['GET'])
@require_role('admin')
def get_periods():
    user = get_current_user()
    org = _get_or_create_org(user)
    periods = ShiftPeriod.query.filter_by(organization_id=org.id).order_by(
        ShiftPeriod.start_date.desc()
    ).all()
    return jsonify([p.to_dict() for p in periods])


@api_admin_bp.route('/periods', methods=['POST'])
@require_role('admin')
@limiter.limit("20 per minute")
def create_period():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")

    from app.utils.validators import parse_date
    start = parse_date(data.get('start_date'))
    end = parse_date(data.get('end_date'))

    if not start or not end:
        return error_response("start_date and end_date required (YYYY-MM-DD)", 400)
    if start >= end:
        return error_response("start_date must be before end_date", 400)
    if not data.get('name'):
        return error_response("name is required", 400)

    try:
        validate_text_length(data['name'], 'name', 200)
    except ValueError as e:
        return error_response(str(e), 400, code="VALIDATION_ERROR")

    deadline = None
    if data.get('submission_deadline'):
        try:
            deadline = datetime.fromisoformat(data['submission_deadline'])
        except ValueError:
            pass

    period = ShiftPeriod(
        organization_id=org.id,
        name=data['name'],
        start_date=start,
        end_date=end,
        submission_deadline=deadline,
        status='draft',
        created_by=user.id,
    )
    db.session.add(period)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify(period.to_dict()), 201


@api_admin_bp.route('/periods/<int:period_id>', methods=['PUT'])
@require_role('admin')
def update_period(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")
    if data.get('name'):
        period.name = data['name']
    if data.get('status'):
        allowed_statuses = ['draft', 'open', 'closed']
        if data['status'] not in allowed_statuses:
            return error_response(f"Invalid status. Allowed: {allowed_statuses}", 400)
        period.status = data['status']
    if data.get('submission_deadline'):
        try:
            period.submission_deadline = datetime.fromisoformat(data['submission_deadline'])
        except ValueError:
            pass

    if data.get('name'):
        try:
            validate_text_length(data['name'], 'name', 200)
        except ValueError as e:
            return error_response(str(e), 400, code="VALIDATION_ERROR")

    from app.utils.validators import parse_date
    if data.get('start_date'):
        d = parse_date(data['start_date'])
        if d:
            period.start_date = d
    if data.get('end_date'):
        d = parse_date(data['end_date'])
        if d:
            period.end_date = d

    # Validate date order after any updates
    if period.start_date >= period.end_date:
        return error_response("start_date must be before end_date", 400)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify(period.to_dict())


# --- Period Opening Hours ---

@api_admin_bp.route('/periods/<int:period_id>/opening-hours', methods=['GET'])
@require_role('admin')
def get_period_opening_hours(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    hours = get_opening_hours_for_period(
        period.organization_id, period.start_date, period.end_date
    )
    return jsonify(hours)


# --- Submissions (view) ---

@api_admin_bp.route('/periods/<int:period_id>/submissions', methods=['GET'])
@require_role('admin')
def get_period_submissions(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    return jsonify(get_submissions_for_period(period_id))


# --- Schedule Building ---

@api_admin_bp.route('/periods/<int:period_id>/schedule', methods=['GET'])
@require_role('admin')
def get_schedule(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    schedule = ShiftSchedule.query.filter_by(shift_period_id=period_id).order_by(
        ShiftSchedule.created_at.desc()
    ).first()
    if not schedule:
        return jsonify(None)

    data = schedule.to_dict()
    data['entries'] = [e.to_dict() for e in schedule.entries.all()]
    data['hours_summary'] = get_worker_hours_summary(schedule.id)
    data['history'] = [h.to_dict() for h in schedule.history.order_by(
        db.text('performed_at desc')
    ).all()]
    return jsonify(data)


@api_admin_bp.route('/periods/<int:period_id>/schedule', methods=['POST'])
@require_role('admin')
@limiter.limit("30 per minute")
def save_period_schedule(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")
    entries = data.get('entries', [])

    try:
        schedule = save_schedule(period_id, user.id, entries, organization_id=org.id)
    except ValueError as e:
        current_app.logger.info(
            "Schedule save validation error: period_id=%s user_id=%s error=%s",
            period_id, user.id, str(e),
        )
        return error_response(str(e), 400, code="VALIDATION_ERROR")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(
            "Schedule save unexpected error: period_id=%s user_id=%s", period_id, user.id,
        )
        return error_response("スケジュールの保存に失敗しました", 500, code="INTERNAL_ERROR")
    result = schedule.to_dict()
    result['entries'] = [e.to_dict() for e in schedule.entries.all()]
    return jsonify(result)


@api_admin_bp.route('/periods/<int:period_id>/schedule/submit', methods=['POST'])
@require_role('admin')
@limiter.limit("10 per minute")
def submit_schedule_for_approval(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    schedule = ShiftSchedule.query.filter_by(shift_period_id=period_id).order_by(
        ShiftSchedule.created_at.desc()
    ).first()
    if not schedule:
        return error_response("No schedule found", 404, code="NOT_FOUND")

    result, error = submit_for_approval(schedule.id, user)
    if error:
        return error_response(error, 400)
    return jsonify(result.to_dict())


@api_admin_bp.route('/periods/<int:period_id>/schedule/confirm', methods=['POST'])
@require_role('admin')
def confirm_period_schedule(period_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    schedule = ShiftSchedule.query.filter_by(shift_period_id=period_id).order_by(
        ShiftSchedule.created_at.desc()
    ).first()
    if not schedule:
        return error_response("No schedule found", 404, code="NOT_FOUND")

    result, error = confirm_schedule(schedule.id, user)
    if error:
        return error_response(error, 400)

    # Sync to Google Calendar
    try:
        sync_results = _sync_schedule_to_calendar(result, user)
    except CredentialsExpiredError as e:
        # Schedule is already confirmed (committed above); calendar sync failed.
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")

    data = result.to_dict()
    data['sync_results'] = sync_results
    return jsonify(data)


def _sync_schedule_to_calendar(schedule, admin_user):
    """Sync confirmed schedule entries to workers' Google Calendars."""
    results = []
    entries = schedule.entries.all()

    try:
        credentials = get_credentials_for_user(admin_user)
    except CredentialsExpiredError:
        raise  # Let caller return standard error_response
    except Exception as e:
        current_app.logger.error(f"Failed to get admin credentials: {e}")
        return [{"error": "認証情報の取得に失敗しました"}]

    if not credentials:
        return [{"error": "Admin has no OAuth credentials"}]

    for entry in entries:
        worker = db.session.get(User, entry.user_id)
        if not worker:
            results.append({"user_id": entry.user_id, "error": "User not found"})
            continue

        summary = f"シフト: {worker.display_name or worker.email}"
        start_dt = f"{entry.shift_date.isoformat()}T{entry.start_time}:00"
        end_dt = f"{entry.shift_date.isoformat()}T{entry.end_time}:00"

        try:
            calendar_id = worker.email
            event_id = create_event(
                credentials, calendar_id, summary, start_dt, end_dt,
                description="シフリーにより自動作成"
            )
            entry.calendar_event_id = event_id
            entry.synced_at = datetime.utcnow()
            results.append({"user_id": entry.user_id, "event_id": event_id, "success": True})
        except Exception as e:
            results.append({"user_id": entry.user_id, "error": str(e)})

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return results


# --- Worker History ---

@api_admin_bp.route('/workers', methods=['GET'])
@require_role('admin')
def get_workers():
    user = get_current_user()
    org = _get_or_create_org(user)
    workers = User.query.filter_by(organization_id=org.id, role='worker', is_active=True).all()
    return jsonify([{
        'id': w.id,
        'email': w.email,
        'display_name': w.display_name,
    } for w in workers])


@api_admin_bp.route('/workers/<int:worker_id>/history', methods=['GET'])
@require_role('admin')
def get_worker_history(worker_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    worker = db.session.get(User, worker_id)
    if not worker or worker.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")
    entries = ShiftScheduleEntry.query.filter_by(user_id=worker_id).order_by(
        ShiftScheduleEntry.shift_date.desc()
    ).limit(50).all()
    return jsonify([e.to_dict() for e in entries])


# --- Organization Members ---

@api_admin_bp.route('/members', methods=['GET'])
@require_role('admin')
def get_members():
    user = get_current_user()
    org = _get_or_create_org(user)
    members = OrganizationMember.query.filter_by(
        organization_id=org.id, is_active=True
    ).all()
    return jsonify([m.to_dict() for m in members])


@api_admin_bp.route('/members/<int:member_id>/role', methods=['PUT'])
@require_role('admin')
def update_member_role(member_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    member = db.session.get(OrganizationMember, member_id)
    if not member or member.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    data = request.get_json(silent=True)
    if not data or not data.get('role'):
        return error_response("role is required", 400)

    new_role = data['role']
    if new_role not in ('admin', 'owner', 'worker'):
        return error_response("Invalid role. Allowed: admin, owner, worker", 400)

    # Prevent removing last admin
    if member.role == 'admin' and new_role != 'admin':
        admin_count = OrganizationMember.query.filter_by(
            organization_id=org.id, role='admin', is_active=True
        ).count()
        if admin_count <= 1:
            return error_response("Cannot remove the last admin", 400)

    old_role = member.role
    member.role = new_role
    member.sync_to_user()
    log_audit(
        action='ROLE_CHANGED',
        resource_type='OrganizationMember',
        resource_id=member.id,
        actor_id=user.id,
        organization_id=org.id,
        old_values={'role': old_role},
        new_values={'role': new_role},
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify(member.to_dict())


@api_admin_bp.route('/members/<int:member_id>', methods=['DELETE'])
@require_role('admin')
def remove_member(member_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    member = db.session.get(OrganizationMember, member_id)
    if not member or member.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    # Prevent self-removal
    if member.user_id == user.id:
        return error_response("Cannot remove yourself", 400)

    # Prevent removing last admin
    if member.role == 'admin':
        admin_count = OrganizationMember.query.filter_by(
            organization_id=org.id, role='admin', is_active=True
        ).count()
        if admin_count <= 1:
            return error_response("Cannot remove the last admin", 400)

    member.is_active = False
    log_audit(
        action='MEMBER_REMOVED',
        resource_type='OrganizationMember',
        resource_id=member.id,
        actor_id=user.id,
        organization_id=org.id,
        old_values={'role': member.role, 'user_email': member.user.email if member.user else None},
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return '', 204


# --- Invitation Tokens ---

@api_admin_bp.route('/invitations', methods=['GET'])
@require_role('admin')
def get_invitations():
    user = get_current_user()
    org = _get_or_create_org(user)
    tokens = InvitationToken.query.filter_by(
        organization_id=org.id
    ).order_by(InvitationToken.created_at.desc()).limit(50).all()
    return jsonify([t.to_dict() for t in tokens])


@api_admin_bp.route('/invitations', methods=['POST'])
@require_role('admin')
def create_invitation():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")

    role = data.get('role', 'worker')
    if role not in ('admin', 'owner', 'worker'):
        return error_response("Invalid role. Allowed: admin, owner, worker", 400)

    email = data.get('email')  # optional: restrict to specific email
    expires_hours = data.get('expires_hours', 72)
    if not isinstance(expires_hours, (int, float)) or expires_hours < 1 or expires_hours > 720:
        return error_response("expires_hours must be between 1 and 720", 400)

    token = InvitationToken(
        organization_id=org.id,
        role=role,
        email=email.strip().lower() if email else None,
        created_by=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
    )
    db.session.add(token)
    db.session.flush()
    log_audit(
        action='INVITATION_CREATED',
        resource_type='InvitationToken',
        resource_id=token.id,
        actor_id=user.id,
        organization_id=org.id,
        new_values={'role': role, 'email': email, 'expires_hours': expires_hours},
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")

    # Send invitation email if email is specified
    if email:
        try:
            from app.services.notification_service import notify_invitation_created
            base_url = request.host_url.rstrip('/')
            invite_url = f"{base_url}/auth/invite/{token.token}"
            notify_invitation_created(
                to_email=token.email,
                org_name=org.name,
                inviter_name=user.display_name or user.email,
                role=token.role,
                invite_url=invite_url,
                expires_at=token.expires_at,
                organization_id=org.id,
                created_by=user.id,
            )
        except Exception as e:
            current_app.logger.warning("Failed to send invitation email: %s", e)

    return jsonify(token.to_dict()), 201


@api_admin_bp.route('/invitations/<int:token_id>', methods=['DELETE'])
@require_role('admin')
def revoke_invitation(token_id):
    user = get_current_user()
    org = _get_or_create_org(user)
    token = db.session.get(InvitationToken, token_id)
    if not token or token.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    if token.used_at:
        return error_response("Token already used", 400)

    # Expire the token immediately
    token.expires_at = datetime.utcnow()
    log_audit(
        action='INVITATION_REVOKED',
        resource_type='InvitationToken',
        resource_id=token.id,
        actor_id=user.id,
        organization_id=org.id,
        old_values={'role': token.role, 'email': token.email},
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return '', 204


# --- Invite Code (organization-wide link) ---

@api_admin_bp.route('/invite-code', methods=['GET'])
@require_role('admin')
def get_invite_code():
    user = get_current_user()
    org = _get_or_create_org(user)
    return jsonify({
        'invite_code': org.invite_code,
        'invite_code_enabled': org.invite_code_enabled,
        'organization_name': org.name,
    })


@api_admin_bp.route('/invite-code', methods=['POST'])
@require_role('admin')
def generate_invite_code():
    """Generate or regenerate the organization invite code."""
    user = get_current_user()
    org = _get_or_create_org(user)
    org.invite_code = secrets.token_urlsafe(16)
    org.invite_code_enabled = True
    log_audit(
        action='INVITE_CODE_GENERATED',
        resource_type='Organization',
        resource_id=org.id,
        actor_id=user.id,
        organization_id=org.id,
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify({
        'invite_code': org.invite_code,
        'invite_code_enabled': org.invite_code_enabled,
    })


@api_admin_bp.route('/invite-code', methods=['PUT'])
@require_role('admin')
def update_invite_code():
    """Enable or disable the invite code."""
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)
    if not data or 'enabled' not in data:
        return error_response("enabled is required", 400, code="BAD_REQUEST")

    if not isinstance(data['enabled'], bool):
        return error_response("enabled must be a boolean", 400, code="VALIDATION_ERROR")

    old_enabled = org.invite_code_enabled
    org.invite_code_enabled = data['enabled']
    log_audit(
        action='INVITE_CODE_TOGGLED',
        resource_type='Organization',
        resource_id=org.id,
        actor_id=user.id,
        organization_id=org.id,
        old_values={'enabled': old_enabled},
        new_values={'enabled': data['enabled']},
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")
    return jsonify({
        'invite_code': org.invite_code,
        'invite_code_enabled': org.invite_code_enabled,
    })


# --- Vacancy Management ---

@api_admin_bp.route('/vacancy/candidates/<int:entry_id>', methods=['GET'])
@require_role('admin')
def get_vacancy_candidates(entry_id):
    """Get list of candidate workers for a vacancy."""
    user = get_current_user()
    org = _get_or_create_org(user)
    entry = db.session.get(ShiftScheduleEntry, entry_id)
    if not entry:
        return error_response("Not found", 404, code="NOT_FOUND")
    schedule = db.session.get(ShiftSchedule, entry.schedule_id)
    if not schedule:
        return error_response("Not found", 404, code="NOT_FOUND")
    period = db.session.get(ShiftPeriod, schedule.shift_period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    from app.services.vacancy_service import find_candidates
    candidates = find_candidates(entry_id, org.id)
    return jsonify(candidates)


@api_admin_bp.route('/vacancy', methods=['POST'])
@require_role('admin')
@limiter.limit("20 per minute")
def create_vacancy():
    """Create a new vacancy request."""
    user = get_current_user()
    data = request.get_json(silent=True)
    if not data or not data.get('schedule_entry_id'):
        return error_response("schedule_entry_id is required", 400, code="BAD_REQUEST")

    from app.services.vacancy_service import create_vacancy_request
    vacancy, error = create_vacancy_request(
        data['schedule_entry_id'],
        data.get('reason', ''),
        user,
    )
    if error:
        return error_response(error, 400)
    return jsonify(vacancy.to_dict()), 201


@api_admin_bp.route('/vacancy/<int:vacancy_id>/notify', methods=['POST'])
@require_role('admin')
@limiter.limit("10 per minute")
def notify_vacancy_candidates(vacancy_id):
    """Send notification emails to selected candidates."""
    user = get_current_user()
    data = request.get_json(silent=True)
    if not data or not data.get('candidate_user_ids'):
        return error_response("candidate_user_ids is required", 400, code="BAD_REQUEST")

    base_url = request.host_url.rstrip('/')
    from app.services.vacancy_service import send_vacancy_notifications
    result, error = send_vacancy_notifications(
        vacancy_id, data['candidate_user_ids'], base_url,
    )
    if error:
        return error_response(error, 400)
    return jsonify(result)


@api_admin_bp.route('/vacancy/<int:vacancy_id>', methods=['DELETE'])
@require_role('admin')
def cancel_vacancy(vacancy_id):
    """Cancel a vacancy request."""
    user = get_current_user()
    from app.services.vacancy_service import cancel_vacancy_request
    vacancy, error = cancel_vacancy_request(vacancy_id, user)
    if error:
        return error_response(error, 400)
    return jsonify(vacancy.to_dict())


@api_admin_bp.route('/vacancy', methods=['GET'])
@require_role('admin')
def get_vacancies():
    """Get list of vacancy requests for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    from app.models.vacancy import VacancyRequest
    vacancies = VacancyRequest.query.join(
        ShiftScheduleEntry, VacancyRequest.schedule_entry_id == ShiftScheduleEntry.id
    ).join(
        ShiftSchedule, ShiftScheduleEntry.schedule_id == ShiftSchedule.id
    ).join(
        ShiftPeriod, ShiftSchedule.shift_period_id == ShiftPeriod.id
    ).filter(
        ShiftPeriod.organization_id == org.id,
    ).order_by(VacancyRequest.created_at.desc()).limit(50).all()
    return jsonify([v.to_dict() for v in vacancies])


@api_admin_bp.route('/change-log', methods=['GET'])
@require_role('admin')
def get_change_log():
    """Get shift change log for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    from app.models.vacancy import ShiftChangeLog
    logs = ShiftChangeLog.query.join(
        ShiftScheduleEntry, ShiftChangeLog.schedule_entry_id == ShiftScheduleEntry.id
    ).join(
        ShiftSchedule, ShiftScheduleEntry.schedule_id == ShiftSchedule.id
    ).join(
        ShiftPeriod, ShiftSchedule.shift_period_id == ShiftPeriod.id
    ).filter(
        ShiftPeriod.organization_id == org.id,
    ).order_by(ShiftChangeLog.performed_at.desc()).limit(50).all()
    return jsonify([l.to_dict() for l in logs])


# --- Sync Settings ---

@api_admin_bp.route('/sync-settings', methods=['GET'])
@require_role('admin')
def get_sync_settings():
    """Get calendar sync settings for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    return jsonify({
        'calendar_sync_keyword': org.get_setting('calendar_sync_keyword', '営業時間'),
        'calendar_setup_dismissed': org.get_setting('calendar_setup_dismissed', False),
    })


@api_admin_bp.route('/sync-settings', methods=['PUT'])
@require_role('admin')
def update_sync_settings():
    """Update calendar sync settings for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")

    if 'calendar_sync_keyword' in data:
        keyword = data['calendar_sync_keyword']
        if not keyword or not isinstance(keyword, str) or len(keyword.strip()) == 0:
            return error_response("calendar_sync_keyword must be a non-empty string", 400, code="VALIDATION_ERROR")
        if len(keyword) > 100:
            return error_response("calendar_sync_keyword must be 100 characters or less", 400, code="VALIDATION_ERROR")
        org.set_setting('calendar_sync_keyword', keyword.strip())

    if 'calendar_setup_dismissed' in data:
        org.set_setting('calendar_setup_dismissed', bool(data['calendar_setup_dismissed']))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")

    return jsonify({
        'calendar_sync_keyword': org.get_setting('calendar_sync_keyword', '営業時間'),
        'calendar_setup_dismissed': org.get_setting('calendar_setup_dismissed', False),
    })


@api_admin_bp.route('/calendars', methods=['GET'])
@require_role('admin')
def list_admin_calendars():
    """List Google Calendars accessible by the admin user."""
    user = get_current_user()
    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except Exception as e:
        current_app.logger.error(f"Credential error: {e}")
        return error_response("認証エラーが発生しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("Google認証情報がありません。再ログインしてください。", 401, code="AUTH_REQUIRED")

    from app.services.calendar_service import list_calendars
    try:
        calendars = list_calendars(credentials)
    except Exception as e:
        current_app.logger.error(f"Failed to list calendars: {e}")
        return error_response("カレンダー一覧の取得に失敗しました", 500, code="INTERNAL_ERROR")

    return jsonify(calendars)


# --- Reminder Settings ---

@api_admin_bp.route('/reminder-settings', methods=['GET'])
@require_role('admin')
def get_reminder_settings():
    """Get reminder settings for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    return jsonify({
        'reminder_days_before_deadline': org.get_setting('reminder_days_before_deadline', 1),
        'reminder_time_deadline': org.get_setting('reminder_time_deadline', '09:00'),
        'reminder_days_before_shift': org.get_setting('reminder_days_before_shift', 1),
        'reminder_time_shift': org.get_setting('reminder_time_shift', '21:00'),
    })


@api_admin_bp.route('/reminder-settings', methods=['PUT'])
@require_role('admin')
def update_reminder_settings():
    """Update reminder settings for the organization."""
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")

    allowed_keys = {
        'reminder_days_before_deadline', 'reminder_time_deadline',
        'reminder_days_before_shift', 'reminder_time_shift',
    }
    for key in allowed_keys:
        if key in data:
            org.set_setting(key, data[key])

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Database error", 500, code="INTERNAL_ERROR")

    return jsonify({
        'reminder_days_before_deadline': org.get_setting('reminder_days_before_deadline', 1),
        'reminder_time_deadline': org.get_setting('reminder_time_deadline', '09:00'),
        'reminder_days_before_shift': org.get_setting('reminder_days_before_shift', 1),
        'reminder_time_shift': org.get_setting('reminder_time_shift', '21:00'),
    })


@api_admin_bp.route('/reminders/send/<int:period_id>', methods=['POST'])
@require_role('admin')
@limiter.limit("5 per minute")
def send_period_reminder(period_id):
    """Manually send submission reminders for a specific period."""
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    from app.services.reminder_service import send_submission_reminder_for_period
    result, error = send_submission_reminder_for_period(period_id, user)
    if error:
        return error_response(error, 400)
    return jsonify(result)


@api_admin_bp.route('/reminders/stats/<int:period_id>', methods=['GET'])
@require_role('admin')
def get_period_reminder_stats(period_id):
    """Get reminder statistics for a specific period."""
    user = get_current_user()
    org = _get_or_create_org(user)
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != org.id:
        return error_response("Not found", 404, code="NOT_FOUND")

    from app.services.reminder_service import get_reminder_stats
    stats = get_reminder_stats(period_id)
    if stats is None:
        return error_response("Not found", 404, code="NOT_FOUND")
    return jsonify(stats)
