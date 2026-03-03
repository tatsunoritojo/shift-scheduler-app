from flask import Blueprint, request, jsonify

from app.extensions import db, limiter
from app.middleware.auth_middleware import require_role, get_current_user
from app.utils.errors import error_response
from app.models.shift import ShiftSchedule, ShiftScheduleEntry, ShiftPeriod
from app.services.shift_service import get_worker_hours_summary
from app.services.approval_service import approve_schedule, reject_schedule

api_owner_bp = Blueprint('api_owner', __name__, url_prefix='/api/owner')


@api_owner_bp.route('/pending-approvals', methods=['GET'])
@require_role('owner')
def get_pending_approvals():
    user = get_current_user()
    schedules = ShiftSchedule.query.filter_by(status='pending_approval').join(
        ShiftPeriod
    ).filter(
        ShiftPeriod.organization_id == user.organization_id
    ).all()

    result = []
    for s in schedules:
        data = s.to_dict()
        data['period'] = s.period.to_dict() if s.period else None
        data['creator_name'] = s.creator.display_name if s.creator else None
        result.append(data)

    return jsonify(result)


@api_owner_bp.route('/schedules/<int:schedule_id>', methods=['GET'])
@require_role('owner')
def get_schedule_detail(schedule_id):
    user = get_current_user()
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or not schedule.period or schedule.period.organization_id != user.organization_id:
        return error_response("Not found", 404, code="NOT_FOUND")

    data = schedule.to_dict()
    data['period'] = schedule.period.to_dict() if schedule.period else None
    data['entries'] = [e.to_dict() for e in schedule.entries.all()]
    data['hours_summary'] = get_worker_hours_summary(schedule.id)
    data['history'] = [h.to_dict() for h in schedule.history.order_by(
        db.text('performed_at desc')
    ).all()]
    return jsonify(data)


@api_owner_bp.route('/schedules/<int:schedule_id>/approve', methods=['POST'])
@require_role('owner')
@limiter.limit("10 per minute")
def approve(schedule_id):
    user = get_current_user()
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or not schedule.period or schedule.period.organization_id != user.organization_id:
        return error_response("Not found", 404, code="NOT_FOUND")
    data = request.get_json(silent=True) or {}
    comment = data.get('comment')

    result, error = approve_schedule(schedule_id, user, comment)
    if error:
        return error_response(error, 400)
    return jsonify(result.to_dict())


@api_owner_bp.route('/schedules/<int:schedule_id>/reject', methods=['POST'])
@require_role('owner')
@limiter.limit("10 per minute")
def reject(schedule_id):
    user = get_current_user()
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or not schedule.period or schedule.period.organization_id != user.organization_id:
        return error_response("Not found", 404, code="NOT_FOUND")
    data = request.get_json(silent=True) or {}
    comment = data.get('comment')

    result, error = reject_schedule(schedule_id, user, comment)
    if error:
        return error_response(error, 400)
    return jsonify(result.to_dict())
