from flask import Blueprint, request, jsonify, session
from datetime import datetime

from app.extensions import db
from app.middleware.auth_middleware import require_role, get_current_user
from app.models.organization import Organization
from app.models.opening_hours import OpeningHours, OpeningHoursException
from app.models.shift import ShiftPeriod, ShiftSchedule, ShiftScheduleEntry
from app.models.user import User
from app.services.shift_service import (
    get_submissions_for_period, save_schedule, get_worker_hours_summary,
    get_opening_hours_for_period,
)
from app.services.approval_service import submit_for_approval, confirm_schedule
from app.services.auth_service import get_credentials_for_user
from app.services.calendar_service import create_event

api_admin_bp = Blueprint('api_admin', __name__, url_prefix='/api/admin')


def _get_or_create_org(user):
    """Get user's organization or create a default one."""
    if user.organization_id:
        return db.session.get(Organization, user.organization_id)
    org = Organization.query.first()
    if not org:
        org = Organization(name='Default', admin_email=user.email)
        db.session.add(org)
        db.session.commit()
    if not user.organization_id:
        user.organization_id = org.id
        db.session.commit()
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
    data = request.get_json()

    if not data or not isinstance(data, list):
        return jsonify({"error": "Expected array of opening hours"}), 400

    for item in data:
        dow = item.get('day_of_week')
        if dow is None or dow < 0 or dow > 6:
            continue

        existing = OpeningHours.query.filter_by(
            organization_id=org.id, day_of_week=dow
        ).first()

        if existing:
            existing.start_time = item.get('start_time', '09:00')
            existing.end_time = item.get('end_time', '21:00')
            existing.is_closed = item.get('is_closed', False)
        else:
            oh = OpeningHours(
                organization_id=org.id,
                day_of_week=dow,
                start_time=item.get('start_time', '09:00'),
                end_time=item.get('end_time', '21:00'),
                is_closed=item.get('is_closed', False),
            )
            db.session.add(oh)

    db.session.commit()
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
    data = request.get_json()

    if not data or not data.get('exception_date'):
        return jsonify({"error": "exception_date is required"}), 400

    from app.utils.validators import parse_date
    exc_date = parse_date(data['exception_date'])
    if not exc_date:
        return jsonify({"error": "Invalid date format"}), 400

    exc = OpeningHoursException(
        organization_id=org.id,
        exception_date=exc_date,
        start_time=data.get('start_time'),
        end_time=data.get('end_time'),
        is_closed=data.get('is_closed', False),
        reason=data.get('reason'),
        source=data.get('source', 'manual'),
    )
    db.session.add(exc)
    db.session.commit()
    return jsonify(exc.to_dict()), 201


@api_admin_bp.route('/opening-hours/exceptions/<int:exc_id>', methods=['DELETE'])
@require_role('admin')
def delete_exception(exc_id):
    exc = db.session.get(OpeningHoursException, exc_id)
    if not exc:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(exc)
    db.session.commit()
    return '', 204


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
def create_period():
    user = get_current_user()
    org = _get_or_create_org(user)
    data = request.get_json()

    from app.utils.validators import parse_date
    start = parse_date(data.get('start_date'))
    end = parse_date(data.get('end_date'))

    if not start or not end:
        return jsonify({"error": "start_date and end_date required (YYYY-MM-DD)"}), 400
    if not data.get('name'):
        return jsonify({"error": "name is required"}), 400

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
        status=data.get('status', 'draft'),
        created_by=user.id,
    )
    db.session.add(period)
    db.session.commit()
    return jsonify(period.to_dict()), 201


@api_admin_bp.route('/periods/<int:period_id>', methods=['PUT'])
@require_role('admin')
def update_period(period_id):
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json()
    if data.get('name'):
        period.name = data['name']
    if data.get('status'):
        period.status = data['status']
    if data.get('submission_deadline'):
        try:
            period.submission_deadline = datetime.fromisoformat(data['submission_deadline'])
        except ValueError:
            pass

    from app.utils.validators import parse_date
    if data.get('start_date'):
        d = parse_date(data['start_date'])
        if d:
            period.start_date = d
    if data.get('end_date'):
        d = parse_date(data['end_date'])
        if d:
            period.end_date = d

    db.session.commit()
    return jsonify(period.to_dict())


# --- Period Opening Hours ---

@api_admin_bp.route('/periods/<int:period_id>/opening-hours', methods=['GET'])
@require_role('admin')
def get_period_opening_hours(period_id):
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return jsonify({"error": "Not found"}), 404

    hours = get_opening_hours_for_period(
        period.organization_id, period.start_date, period.end_date
    )
    return jsonify(hours)


# --- Submissions (view) ---

@api_admin_bp.route('/periods/<int:period_id>/submissions', methods=['GET'])
@require_role('admin')
def get_period_submissions(period_id):
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return jsonify({"error": "Not found"}), 404
    return jsonify(get_submissions_for_period(period_id))


# --- Schedule Building ---

@api_admin_bp.route('/periods/<int:period_id>/schedule', methods=['GET'])
@require_role('admin')
def get_schedule(period_id):
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
def save_period_schedule(period_id):
    user = get_current_user()
    data = request.get_json()
    entries = data.get('entries', [])

    schedule = save_schedule(period_id, user.id, entries)
    result = schedule.to_dict()
    result['entries'] = [e.to_dict() for e in schedule.entries.all()]
    return jsonify(result)


@api_admin_bp.route('/periods/<int:period_id>/schedule/submit', methods=['POST'])
@require_role('admin')
def submit_schedule_for_approval(period_id):
    user = get_current_user()
    schedule = ShiftSchedule.query.filter_by(shift_period_id=period_id).order_by(
        ShiftSchedule.created_at.desc()
    ).first()
    if not schedule:
        return jsonify({"error": "No schedule found"}), 404

    result, error = submit_for_approval(schedule.id, user)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result.to_dict())


@api_admin_bp.route('/periods/<int:period_id>/schedule/confirm', methods=['POST'])
@require_role('admin')
def confirm_period_schedule(period_id):
    user = get_current_user()
    schedule = ShiftSchedule.query.filter_by(shift_period_id=period_id).order_by(
        ShiftSchedule.created_at.desc()
    ).first()
    if not schedule:
        return jsonify({"error": "No schedule found"}), 404

    result, error = confirm_schedule(schedule.id, user)
    if error:
        return jsonify({"error": error}), 400

    # Sync to Google Calendar
    sync_results = _sync_schedule_to_calendar(result, user)

    data = result.to_dict()
    data['sync_results'] = sync_results
    return jsonify(data)


def _sync_schedule_to_calendar(schedule, admin_user):
    """Sync confirmed schedule entries to workers' Google Calendars."""
    results = []
    entries = schedule.entries.all()

    try:
        credentials = get_credentials_for_user(admin_user)
    except Exception as e:
        return [{"error": f"Failed to get admin credentials: {e}"}]

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
                description=f"シフト管理システムにより自動作成"
            )
            entry.calendar_event_id = event_id
            entry.synced_at = datetime.utcnow()
            results.append({"user_id": entry.user_id, "event_id": event_id, "success": True})
        except Exception as e:
            results.append({"user_id": entry.user_id, "error": str(e)})

    db.session.commit()
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
    entries = ShiftScheduleEntry.query.filter_by(user_id=worker_id).order_by(
        ShiftScheduleEntry.shift_date.desc()
    ).limit(50).all()
    return jsonify([e.to_dict() for e in entries])
