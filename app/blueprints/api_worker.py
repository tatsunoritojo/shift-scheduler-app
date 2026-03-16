from datetime import datetime

from flask import Blueprint, request, jsonify, session, current_app

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_role, get_current_user
from app.utils.errors import error_response
from app.models.shift import ShiftPeriod, ShiftSubmission, ShiftSchedule, ShiftScheduleEntry
from app.models.user import User
from app.services.shift_service import (
    get_opening_hours_for_period, create_or_update_submission,
)
from app.services.auth_service import get_credentials_for_user, CredentialsExpiredError
from app.services.calendar_service import fetch_events, list_calendars, create_event, classify_calendar_error

api_worker_bp = Blueprint('api_worker', __name__, url_prefix='/api/worker')


@api_worker_bp.route('/periods', methods=['GET'])
@require_role('worker')
def get_open_periods():
    user = get_current_user()
    # Get periods that are open for submission
    periods = ShiftPeriod.query.filter(
        ShiftPeriod.status.in_(['open']),
        ShiftPeriod.organization_id == user.organization_id,
    ).order_by(ShiftPeriod.start_date).all()

    result = []
    for p in periods:
        data = p.to_dict()
        # Check if user already submitted
        sub = ShiftSubmission.query.filter_by(
            shift_period_id=p.id, user_id=user.id
        ).first()
        data['submission_status'] = sub.status if sub else None
        data['submitted_at'] = sub.submitted_at.isoformat() if sub and sub.submitted_at else None
        result.append(data)

    return jsonify(result)


@api_worker_bp.route('/periods/<int:period_id>/opening-hours', methods=['GET'])
@require_role('worker')
def get_period_opening_hours(period_id):
    user = get_current_user()
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != user.organization_id:
        return error_response("Not found", 404, code="NOT_FOUND")

    hours = get_opening_hours_for_period(
        period.organization_id, period.start_date, period.end_date
    )
    return jsonify(hours)


@api_worker_bp.route('/calendars', methods=['GET'])
@require_role('worker')
def get_worker_calendars():
    user = get_current_user()

    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except RuntimeError as e:
        current_app.logger.error(f"Credential error for user {user.id}: {e}")
        return error_response("認証情報の取得に失敗しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("No credentials found", 404, code="NOT_FOUND")

    try:
        calendars = list_calendars(credentials)
        return jsonify(calendars)
    except Exception as e:
        current_app.logger.error(f"Calendar list error: {e}")
        return error_response("カレンダー一覧の取得に失敗しました。", 500, code="INTERNAL_ERROR")


@api_worker_bp.route('/calendar/events', methods=['GET'])
@require_role('worker')
def get_worker_calendar_events():
    user = get_current_user()

    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except RuntimeError as e:
        current_app.logger.error(f"Credential error for user {user.id}: {e}")
        return error_response("認証情報の取得に失敗しました。再ログインしてください。", 500, code="INTERNAL_ERROR")

    if not credentials:
        return error_response("No credentials found", 404, code="NOT_FOUND")

    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    calendar_id = request.args.get('calendarId', 'primary')

    if not start_date or not end_date:
        return error_response("startDate and endDate are required", 400, code="VALIDATION_ERROR")

    try:
        events = fetch_events(credentials, start_date, end_date, calendar_id)
        return jsonify(events)
    except Exception as e:
        current_app.logger.error(f"Calendar event fetch error: {e}")
        return error_response("カレンダーイベントの取得に失敗しました。", 500, code="INTERNAL_ERROR")


@api_worker_bp.route('/periods/<int:period_id>/availability', methods=['GET'])
@require_role('worker')
def get_my_submission(period_id):
    user = get_current_user()
    sub = ShiftSubmission.query.filter_by(
        shift_period_id=period_id, user_id=user.id
    ).first()
    if not sub:
        return jsonify(None)

    data = sub.to_dict()
    data['slots'] = [s.to_dict() for s in sub.slots.all()]
    return jsonify(data)


@api_worker_bp.route('/periods/<int:period_id>/availability', methods=['POST'])
@require_role('worker')
@limiter.limit("20 per minute")
def submit_availability(period_id):
    user = get_current_user()
    period = db.session.get(ShiftPeriod, period_id)
    if not period or period.organization_id != user.organization_id:
        return error_response("Period not found", 404, code="NOT_FOUND")
    if period.status != 'open':
        return error_response("Period is not open for submissions", 400, code="VALIDATION_ERROR")

    data = request.get_json(silent=True)
    if not data:
        return error_response("Request body is required", 400, code="BAD_REQUEST")
    slots = data.get('slots', [])
    notes = data.get('notes')

    try:
        submission = create_or_update_submission(period_id, user.id, slots, notes)
    except ValueError as e:
        return error_response(str(e), 400, code="VALIDATION_ERROR")
    result = submission.to_dict()
    result['slots'] = [s.to_dict() for s in submission.slots.all()]
    return jsonify(result), 201


# --- Confirmed Shifts ---

def _sync_meta(entry):
    """Build sync metadata dict from model properties."""
    return {
        'is_synced': entry.is_synced,
        'can_sync': entry.can_sync,
        'sync_status': entry.get_sync_status(),
    }


@api_worker_bp.route('/confirmed-shifts', methods=['GET'])
@require_role('worker')
def get_confirmed_shifts():
    """Return the current worker's confirmed shift entries."""
    user = get_current_user()
    entries = (
        ShiftScheduleEntry.query
        .join(ShiftSchedule, ShiftScheduleEntry.schedule_id == ShiftSchedule.id)
        .join(ShiftPeriod, ShiftSchedule.shift_period_id == ShiftPeriod.id)
        .filter(
            ShiftScheduleEntry.user_id == user.id,
            ShiftSchedule.status == 'confirmed',
            ShiftPeriod.organization_id == user.organization_id,
        )
        .order_by(ShiftScheduleEntry.shift_date)
        .all()
    )
    result = []
    for entry in entries:
        data = entry.to_dict()
        data.update(_sync_meta(entry))
        result.append(data)
    return jsonify(result)


@api_worker_bp.route('/confirmed-shifts/<int:entry_id>/sync', methods=['POST'])
@require_role('worker')
@limiter.limit("30 per minute")
def sync_confirmed_shift(entry_id):
    """Sync a single confirmed shift entry to the worker's Google Calendar."""
    user = get_current_user()

    # Fetch entry with ownership + confirmed status check
    entry = (
        ShiftScheduleEntry.query
        .join(ShiftSchedule, ShiftScheduleEntry.schedule_id == ShiftSchedule.id)
        .join(ShiftPeriod, ShiftSchedule.shift_period_id == ShiftPeriod.id)
        .filter(
            ShiftScheduleEntry.id == entry_id,
            ShiftScheduleEntry.user_id == user.id,
            ShiftSchedule.status == 'confirmed',
            ShiftPeriod.organization_id == user.organization_id,
        )
        .first()
    )
    if not entry:
        return error_response("Shift not found", 404, code="NOT_FOUND")

    # Idempotency: already synced
    if entry.calendar_event_id:
        data = entry.to_dict()
        data.update(_sync_meta(entry))
        data['skipped'] = True
        return jsonify(data)

    # Get worker's own credentials
    try:
        credentials = get_credentials_for_user(user)
    except CredentialsExpiredError as e:
        entry.sync_error = 'CREDENTIALS_EXPIRED'
        db.session.commit()
        return error_response(str(e), 401, code="CREDENTIALS_EXPIRED")
    except Exception as e:
        entry.sync_error = 'CREDENTIALS_UNAVAILABLE'
        db.session.commit()
        return error_response(str(e), 500, code="CREDENTIALS_UNAVAILABLE")

    if not credentials:
        entry.sync_error = 'NO_CREDENTIALS'
        db.session.commit()
        return error_response(
            "Google連携未設定。再ログインしてください。", 401, code="NO_CREDENTIALS"
        )

    # Create calendar event
    summary = f"シフト: {user.display_name or user.email}"
    start_dt = f"{entry.shift_date.isoformat()}T{entry.start_time}:00"
    end_dt = f"{entry.shift_date.isoformat()}T{entry.end_time}:00"

    try:
        event_id = create_event(
            credentials, 'primary', summary, start_dt, end_dt,
            description="シフリーにより自動作成"
        )
    except Exception as e:
        current_app.logger.error("Manual calendar sync failed for user %s entry %s: %s", user.id, entry_id, e)
        error_code = classify_calendar_error(e)
        entry.sync_error = error_code
        db.session.commit()
        status = 401 if error_code == 'CREDENTIALS_EXPIRED' else 500
        return error_response(str(e), status, code=error_code)

    entry.calendar_event_id = event_id
    entry.synced_at = datetime.utcnow()
    entry.sync_error = None
    db.session.commit()

    data = entry.to_dict()
    data.update(_sync_meta(entry))
    return jsonify(data)
