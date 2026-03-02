from flask import Blueprint, request, jsonify, session, current_app

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_role, get_current_user
from app.utils.errors import error_response
from app.models.shift import ShiftPeriod, ShiftSubmission
from app.models.user import User
from app.services.shift_service import (
    get_opening_hours_for_period, create_or_update_submission,
)
from app.services.auth_service import get_credentials_for_user, CredentialsExpiredError
from app.services.calendar_service import fetch_events, list_calendars

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
