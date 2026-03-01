"""Operational dashboard API — metrics for admin monitoring."""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.middleware.auth_middleware import require_role, get_current_user
from app.models.async_task import AsyncTask
from app.models.approval import ApprovalHistory
from app.models.shift import ShiftSchedule
from app.models.opening_hours import SyncOperationLog

api_dashboard_bp = Blueprint('api_dashboard', __name__)


@api_dashboard_bp.route('/api/admin/dashboard/overview', methods=['GET'])
@require_role('admin')
def overview():
    """High-level metrics: task queue health, approval stats, sync status."""
    user = get_current_user()
    org_id = user.organization_id
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # --- Task queue stats (last 24h) ---
    task_stats = (
        db.session.query(AsyncTask.status, func.count(AsyncTask.id))
        .filter(AsyncTask.organization_id == org_id)
        .filter(AsyncTask.created_at >= last_24h)
        .group_by(AsyncTask.status)
        .all()
    )
    task_counts = {status: count for status, count in task_stats}

    # Pending tasks right now (all time)
    pending_now = AsyncTask.query.filter_by(
        organization_id=org_id, status='pending',
    ).count()

    # --- Approval workflow stats (last 7 days) ---
    schedules = (
        ShiftSchedule.query
        .join(ShiftSchedule.period)
        .filter(ShiftSchedule.created_at >= last_7d)
        .filter_by(organization_id=org_id)
        .all()
    )
    approval_stats = {
        'total': len(schedules),
        'draft': sum(1 for s in schedules if s.status == 'draft'),
        'pending_approval': sum(1 for s in schedules if s.status == 'pending_approval'),
        'approved': sum(1 for s in schedules if s.status == 'approved'),
        'rejected': sum(1 for s in schedules if s.status == 'rejected'),
        'confirmed': sum(1 for s in schedules if s.status == 'confirmed'),
    }

    # --- Calendar sync stats (last 7 days) ---
    sync_logs = (
        SyncOperationLog.query
        .filter_by(organization_id=org_id)
        .filter(SyncOperationLog.performed_at >= last_7d)
        .order_by(SyncOperationLog.performed_at.desc())
        .limit(10)
        .all()
    )

    return jsonify({
        'tasks': {
            'last_24h': task_counts,
            'pending_now': pending_now,
        },
        'approvals': approval_stats,
        'recent_syncs': [log.to_dict() for log in sync_logs],
    })


@api_dashboard_bp.route('/api/admin/dashboard/tasks', methods=['GET'])
@require_role('admin')
def task_list():
    """List recent async tasks for the organization."""
    user = get_current_user()
    org_id = user.organization_id
    status_filter = request.args.get('status')
    limit = min(int(request.args.get('limit', 50)), 200)

    query = (
        AsyncTask.query
        .filter_by(organization_id=org_id)
        .order_by(AsyncTask.created_at.desc())
    )
    if status_filter:
        query = query.filter_by(status=status_filter)

    tasks = query.limit(limit).all()
    return jsonify([t.to_dict() for t in tasks])


@api_dashboard_bp.route('/api/admin/dashboard/task-stats', methods=['GET'])
@require_role('admin')
def task_stats():
    """Aggregated task statistics over configurable periods."""
    user = get_current_user()
    org_id = user.organization_id
    days = min(int(request.args.get('days', 7)), 90)
    since = datetime.utcnow() - timedelta(days=days)

    # Success/failure rates by task type
    rows = (
        db.session.query(
            AsyncTask.task_type,
            AsyncTask.status,
            func.count(AsyncTask.id),
        )
        .filter(AsyncTask.organization_id == org_id)
        .filter(AsyncTask.created_at >= since)
        .group_by(AsyncTask.task_type, AsyncTask.status)
        .all()
    )

    stats = {}
    for task_type, status, count in rows:
        if task_type not in stats:
            stats[task_type] = {}
        stats[task_type][status] = count

    # Average retry count for failed tasks
    avg_retries = (
        db.session.query(func.avg(AsyncTask.retry_count))
        .filter(AsyncTask.organization_id == org_id)
        .filter(AsyncTask.created_at >= since)
        .filter(AsyncTask.status.in_(['dead', 'completed']))
        .scalar()
    )

    return jsonify({
        'period_days': days,
        'by_type': stats,
        'avg_retries': round(float(avg_retries or 0), 2),
    })
