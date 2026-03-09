"""Master admin blueprint — system-wide management for the app creator."""

import os
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request, session, send_from_directory, current_app
from sqlalchemy import func, text

from app.extensions import db
from app.models.user import User, UserToken
from app.models.organization import Organization
from app.models.membership import OrganizationMember, InvitationToken
from app.models.shift import (
    ShiftPeriod, ShiftSubmission, ShiftSubmissionSlot,
    ShiftSchedule, ShiftScheduleEntry,
)
from app.models.async_task import AsyncTask
from app.models.audit_log import AuditLog
from app.models.approval import ApprovalHistory
from app.utils.errors import error_response

logger = logging.getLogger(__name__)
api_master_bp = Blueprint('api_master', __name__)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _get_master_emails():
    """Return set of emails allowed to access the master panel."""
    raw = os.environ.get('MASTER_EMAIL', '')
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def _get_master_user():
    """Return current master user or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        return None
    if user.email.lower() not in _get_master_emails():
        return None
    return user


def require_master(f):
    """Require the logged-in user to be a master (app creator)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_master_user()
        if not user:
            user_id = session.get('user_id')
            if not user_id:
                return error_response("Authentication required", 401, code="AUTH_REQUIRED")
            return error_response("Master access required", 403, code="FORBIDDEN")
        return f(*args, **kwargs)
    return decorated


def _log_master_action(action, resource_type=None, resource_id=None,
                       old_values=None, new_values=None):
    """Log a master admin action to AuditLog."""
    user = _get_master_user()
    log = AuditLog(
        organization_id=None,
        actor_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=request.remote_addr,
        status='SUCCESS',
    )
    db.session.add(log)


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@api_master_bp.route('/master')
def master_page():
    """Serve the master admin page."""
    user_id = session.get('user_id')
    if not user_id:
        return current_app.redirect('/login')
    user = db.session.get(User, user_id)
    if not user or user.email.lower() not in _get_master_emails():
        return error_response("Forbidden", 403, code="FORBIDDEN")
    return send_from_directory(current_app.static_folder, 'pages/master.html')


# ---------------------------------------------------------------------------
# API: Overview stats
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/stats')
@require_master
def master_stats():
    """High-level system statistics."""
    users_total = db.session.query(func.count(User.id)).scalar()
    users_active = db.session.query(func.count(User.id)).filter(User.is_active == True).scalar()
    orgs_total = db.session.query(func.count(Organization.id)).scalar()
    orgs_active = db.session.query(func.count(Organization.id)).filter(Organization.is_active == True).scalar()
    members_total = db.session.query(func.count(OrganizationMember.id)).scalar()
    members_active = db.session.query(func.count(OrganizationMember.id)).filter(OrganizationMember.is_active == True).scalar()
    periods_total = db.session.query(func.count(ShiftPeriod.id)).scalar()
    schedules_total = db.session.query(func.count(ShiftSchedule.id)).scalar()
    tasks_pending = db.session.query(func.count(AsyncTask.id)).filter(AsyncTask.status == 'pending').scalar()
    tasks_failed = db.session.query(func.count(AsyncTask.id)).filter(AsyncTask.status.in_(['failed', 'dead'])).scalar()
    invitations_pending = db.session.query(func.count(InvitationToken.id)).filter(InvitationToken.used_at == None).scalar()

    return jsonify({
        'users': {'total': users_total, 'active': users_active},
        'organizations': {'total': orgs_total, 'active': orgs_active},
        'members': {'total': members_total, 'active': members_active},
        'periods': periods_total,
        'schedules': schedules_total,
        'tasks': {'pending': tasks_pending, 'failed': tasks_failed},
        'invitations_pending': invitations_pending,
    })


# ---------------------------------------------------------------------------
# API: Users CRUD
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/users')
@require_master
def list_users():
    """List all users with their memberships and token health."""
    users = User.query.order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        membership = OrganizationMember.query.filter_by(user_id=u.id, is_active=True).first()
        org_name = None
        member_role = None
        if membership:
            org = db.session.get(Organization, membership.organization_id)
            org_name = org.name if org else None
            member_role = membership.role
        token = UserToken.query.filter_by(user_id=u.id).first()
        has_token = token is not None and token.refresh_token is not None
        result.append({
            'id': u.id,
            'email': u.email,
            'display_name': u.display_name,
            'role': u.role,
            'organization_id': u.organization_id,
            'organization_name': org_name,
            'member_role': member_role,
            'is_active': u.is_active,
            'has_token': has_token,
            'token_scopes': token.scopes if token else None,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'updated_at': u.updated_at.isoformat() if u.updated_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/users/<int:user_id>', methods=['PUT'])
@require_master
def update_user(user_id):
    """Update user fields (display_name, is_active)."""
    user = db.session.get(User, user_id)
    if not user:
        return error_response("User not found", 404)
    data = request.get_json(silent=True) or {}
    if 'display_name' in data:
        user.display_name = data['display_name']
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    db.session.commit()
    return jsonify({'ok': True})


@api_master_bp.route('/api/master/users/<int:user_id>', methods=['DELETE'])
@require_master
def deactivate_user(user_id):
    """Deactivate a user (soft delete)."""
    user = db.session.get(User, user_id)
    if not user:
        return error_response("User not found", 404)
    user.is_active = False
    memberships = OrganizationMember.query.filter_by(user_id=user.id, is_active=True).all()
    for m in memberships:
        m.is_active = False
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API: Organizations CRUD
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/organizations')
@require_master
def list_organizations():
    """List all organizations with member counts."""
    orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    result = []
    for o in orgs:
        member_count = OrganizationMember.query.filter_by(
            organization_id=o.id, is_active=True
        ).count()
        result.append({
            'id': o.id,
            'name': o.name,
            'admin_email': o.admin_email,
            'owner_email': o.owner_email,
            'is_active': o.is_active,
            'invite_code': o.invite_code,
            'invite_code_enabled': o.invite_code_enabled,
            'member_count': member_count,
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'updated_at': o.updated_at.isoformat() if o.updated_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/organizations/<int:org_id>', methods=['PUT'])
@require_master
def update_organization(org_id):
    """Update organization fields."""
    org = db.session.get(Organization, org_id)
    if not org:
        return error_response("Organization not found", 404)
    data = request.get_json(silent=True) or {}
    for field in ('name', 'admin_email', 'owner_email', 'is_active', 'invite_code_enabled'):
        if field in data:
            setattr(org, field, data[field])
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API: Members
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/members')
@require_master
def list_members():
    """List all organization members."""
    members = OrganizationMember.query.order_by(OrganizationMember.joined_at.desc()).all()
    result = []
    for m in members:
        user = db.session.get(User, m.user_id)
        org = db.session.get(Organization, m.organization_id)
        result.append({
            'id': m.id,
            'user_id': m.user_id,
            'user_email': user.email if user else None,
            'user_name': user.display_name if user else None,
            'organization_id': m.organization_id,
            'organization_name': org.name if org else None,
            'role': m.role,
            'is_active': m.is_active,
            'joined_at': m.joined_at.isoformat() if m.joined_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/members/<int:member_id>', methods=['PUT'])
@require_master
def update_member(member_id):
    """Update member role or active status."""
    member = OrganizationMember.query.get(member_id)
    if not member:
        return error_response("Member not found", 404)
    data = request.get_json(silent=True) or {}
    if 'role' in data and data['role'] in ('admin', 'owner', 'worker'):
        member.role = data['role']
    if 'is_active' in data:
        member.is_active = bool(data['is_active'])
    member.sync_to_user()
    db.session.commit()
    return jsonify({'ok': True})


# ===========================================================================
# Scenario 1: Dead/Failed Async Tasks — retry, detail, manual cron trigger
# ===========================================================================

@api_master_bp.route('/api/master/tasks')
@require_master
def list_tasks():
    """List async tasks with optional status filter."""
    status = request.args.get('status')
    query = AsyncTask.query
    if status:
        query = query.filter(AsyncTask.status == status)
    tasks = query.order_by(AsyncTask.created_at.desc()).limit(200).all()
    result = []
    for t in tasks:
        result.append({
            'id': t.id,
            'task_type': t.task_type,
            'status': t.status,
            'priority': t.priority,
            'retry_count': t.retry_count,
            'max_retries': t.max_retries,
            'error_message': t.error_message,
            'organization_id': t.organization_id,
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'started_at': t.started_at.isoformat() if t.started_at else None,
            'completed_at': t.completed_at.isoformat() if t.completed_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/tasks/<int:task_id>')
@require_master
def get_task_detail(task_id):
    """Get full task detail including payload."""
    task = db.session.get(AsyncTask, task_id)
    if not task:
        return error_response("Task not found", 404)
    return jsonify({
        'id': task.id,
        'task_type': task.task_type,
        'payload': task.payload,
        'status': task.status,
        'priority': task.priority,
        'retry_count': task.retry_count,
        'max_retries': task.max_retries,
        'error_message': task.error_message,
        'organization_id': task.organization_id,
        'created_by': task.created_by,
        'created_at': task.created_at.isoformat() if task.created_at else None,
        'started_at': task.started_at.isoformat() if task.started_at else None,
        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
        'next_run_at': task.next_run_at.isoformat() if task.next_run_at else None,
    })


@api_master_bp.route('/api/master/tasks/<int:task_id>/retry', methods=['POST'])
@require_master
def retry_task(task_id):
    """Reset a dead/failed task to pending for re-processing."""
    task = db.session.get(AsyncTask, task_id)
    if not task:
        return error_response("Task not found", 404)
    if task.status not in ('dead', 'failed'):
        return error_response("Only dead or failed tasks can be retried", 400)
    old_status = task.status
    task.status = 'pending'
    task.retry_count = 0
    task.error_message = None
    task.next_run_at = datetime.utcnow()
    task.started_at = None
    task.completed_at = None
    _log_master_action('MASTER_TASK_RETRY', 'AsyncTask', task.id,
                       old_values={'status': old_status},
                       new_values={'status': 'pending'})
    db.session.commit()
    return jsonify({'ok': True, 'task_id': task.id})


@api_master_bp.route('/api/master/tasks/process-now', methods=['POST'])
@require_master
def process_tasks_now():
    """Manually trigger async task processing (same as cron)."""
    from app.services.task_runner import process_pending_tasks
    try:
        stats = process_pending_tasks(batch_size=20)
        _log_master_action('MASTER_CRON_TRIGGER', new_values=stats)
        db.session.commit()
        return jsonify(stats)
    except Exception as e:
        logger.exception("Manual task processing failed")
        return error_response(f"Processing error: {str(e)}", 500)


# ===========================================================================
# Scenario 2: OAuth Token Health
# ===========================================================================

@api_master_bp.route('/api/master/token-health')
@require_master
def token_health():
    """Show OAuth token health for all active users."""
    users = User.query.filter_by(is_active=True).all()
    result = {'healthy': 0, 'missing': 0, 'users': []}
    for u in users:
        token = UserToken.query.filter_by(user_id=u.id).first()
        has_token = token is not None and token.refresh_token is not None
        if has_token:
            result['healthy'] += 1
        else:
            result['missing'] += 1
        result['users'].append({
            'id': u.id,
            'email': u.email,
            'display_name': u.display_name,
            'has_token': has_token,
            'scopes': token.scopes if token else None,
            'token_updated_at': token.updated_at.isoformat() if token and token.updated_at else None,
        })
    return jsonify(result)


# ===========================================================================
# Scenario 3: Period & Schedule status override
# ===========================================================================

@api_master_bp.route('/api/master/periods')
@require_master
def list_periods():
    """List all shift periods across all organizations."""
    periods = ShiftPeriod.query.order_by(ShiftPeriod.created_at.desc()).all()
    result = []
    for p in periods:
        org = db.session.get(Organization, p.organization_id)
        submissions_count = ShiftSubmission.query.filter_by(shift_period_id=p.id).count()
        schedule = ShiftSchedule.query.filter_by(shift_period_id=p.id).order_by(
            ShiftSchedule.created_at.desc()
        ).first()
        result.append({
            'id': p.id,
            'name': p.name,
            'organization_id': p.organization_id,
            'organization_name': org.name if org else None,
            'start_date': p.start_date.isoformat() if p.start_date else None,
            'end_date': p.end_date.isoformat() if p.end_date else None,
            'submission_deadline': p.submission_deadline.isoformat() if p.submission_deadline else None,
            'status': p.status,
            'submissions_count': submissions_count,
            'schedule_status': schedule.status if schedule else None,
            'schedule_id': schedule.id if schedule else None,
            'created_at': p.created_at.isoformat() if p.created_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/periods/<int:period_id>/status', methods=['PUT'])
@require_master
def override_period_status(period_id):
    """Force-set period status (master override)."""
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return error_response("Period not found", 404)
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    valid = ('draft', 'open', 'closed', 'finalized')
    if new_status not in valid:
        return error_response(f"Invalid status. Must be one of: {valid}", 400)
    old_status = period.status
    period.status = new_status
    # Also allow extending deadline
    if 'submission_deadline' in data and data['submission_deadline']:
        period.submission_deadline = datetime.fromisoformat(data['submission_deadline'])
    _log_master_action('MASTER_PERIOD_STATUS_OVERRIDE', 'ShiftPeriod', period.id,
                       old_values={'status': old_status},
                       new_values={'status': new_status})
    db.session.commit()
    return jsonify({'ok': True})


@api_master_bp.route('/api/master/schedules')
@require_master
def list_schedules():
    """List all schedules across all organizations."""
    schedules = ShiftSchedule.query.order_by(ShiftSchedule.created_at.desc()).all()
    result = []
    for s in schedules:
        period = db.session.get(ShiftPeriod, s.shift_period_id)
        org = db.session.get(Organization, period.organization_id) if period else None
        entries_count = ShiftScheduleEntry.query.filter_by(schedule_id=s.id).count()
        synced_count = ShiftScheduleEntry.query.filter(
            ShiftScheduleEntry.schedule_id == s.id,
            ShiftScheduleEntry.calendar_event_id != None,
        ).count()
        result.append({
            'id': s.id,
            'period_id': s.shift_period_id,
            'period_name': period.name if period else None,
            'organization_name': org.name if org else None,
            'status': s.status,
            'entries_count': entries_count,
            'synced_count': synced_count,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'approved_at': s.approved_at.isoformat() if s.approved_at else None,
            'confirmed_at': s.confirmed_at.isoformat() if s.confirmed_at else None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/schedules/<int:schedule_id>/status', methods=['PUT'])
@require_master
def override_schedule_status(schedule_id):
    """Force-set schedule status (master override)."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule:
        return error_response("Schedule not found", 404)
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    valid = ('draft', 'pending_approval', 'approved', 'rejected', 'confirmed')
    if new_status not in valid:
        return error_response(f"Invalid status. Must be one of: {valid}", 400)
    old_status = schedule.status
    schedule.status = new_status
    master_user = _get_master_user()
    history = ApprovalHistory(
        schedule_id=schedule.id,
        action='master_override',
        performed_by=master_user.id,
        comment=f"Master override: {old_status} → {new_status}",
    )
    db.session.add(history)
    _log_master_action('MASTER_SCHEDULE_STATUS_OVERRIDE', 'ShiftSchedule', schedule.id,
                       old_values={'status': old_status},
                       new_values={'status': new_status})
    db.session.commit()
    return jsonify({'ok': True})


# ===========================================================================
# Scenario 4: Calendar sync status & re-sync
# ===========================================================================

@api_master_bp.route('/api/master/schedules/<int:schedule_id>/sync-status')
@require_master
def schedule_sync_status(schedule_id):
    """Show sync status for all entries in a schedule."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule:
        return error_response("Schedule not found", 404)
    entries = ShiftScheduleEntry.query.filter_by(schedule_id=schedule_id).all()
    result = []
    for e in entries:
        user = db.session.get(User, e.user_id)
        result.append({
            'id': e.id,
            'user_id': e.user_id,
            'user_name': user.display_name if user else None,
            'user_email': user.email if user else None,
            'shift_date': e.shift_date.isoformat() if e.shift_date else None,
            'start_time': e.start_time,
            'end_time': e.end_time,
            'calendar_event_id': e.calendar_event_id,
            'synced_at': e.synced_at.isoformat() if e.synced_at else None,
            'is_synced': e.calendar_event_id is not None,
        })
    return jsonify(result)


@api_master_bp.route('/api/master/schedules/<int:schedule_id>/resync', methods=['POST'])
@require_master
def resync_schedule(schedule_id):
    """Re-sync all unsynced entries via async task queue."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule:
        return error_response("Schedule not found", 404)
    period = db.session.get(ShiftPeriod, schedule.shift_period_id)

    entries = ShiftScheduleEntry.query.filter(
        ShiftScheduleEntry.schedule_id == schedule_id,
        ShiftScheduleEntry.calendar_event_id == None,
    ).all()

    if not entries:
        return jsonify({'ok': True, 'enqueued': 0, 'message': 'All entries already synced'})

    from app.services.task_runner import enqueue_calendar_sync
    enqueued = 0
    for entry in entries:
        user = db.session.get(User, entry.user_id)
        if not user:
            continue
        summary = f"シフト: {user.display_name or user.email}"
        start_dt = f"{entry.shift_date.isoformat()}T{entry.start_time}:00"
        end_dt = f"{entry.shift_date.isoformat()}T{entry.end_time}:00"
        enqueue_calendar_sync(
            user_id=user.id,
            entry_id=entry.id,
            summary=summary,
            start_datetime=start_dt,
            end_datetime=end_dt,
            calendar_id=user.email,
            organization_id=period.organization_id if period else None,
        )
        enqueued += 1

    _log_master_action('MASTER_SCHEDULE_RESYNC', 'ShiftSchedule', schedule_id,
                       new_values={'enqueued': enqueued})
    db.session.commit()
    return jsonify({'ok': True, 'enqueued': enqueued})


# ===========================================================================
# Scenario 5: Submission compliance monitoring
# ===========================================================================

@api_master_bp.route('/api/master/periods/<int:period_id>/compliance')
@require_master
def period_compliance(period_id):
    """Show submission compliance for a period."""
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return error_response("Period not found", 404)

    # All active workers in the organization
    workers = (
        db.session.query(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(
            OrganizationMember.organization_id == period.organization_id,
            OrganizationMember.is_active == True,
            OrganizationMember.role == 'worker',
            User.is_active == True,
        )
        .all()
    )

    submissions = {
        s.user_id: s for s in
        ShiftSubmission.query.filter_by(shift_period_id=period_id).all()
    }

    submitted = []
    missing = []
    for w in workers:
        sub = submissions.get(w.id)
        if sub and sub.status == 'submitted':
            submitted.append({
                'user_id': w.id,
                'user_name': w.display_name,
                'email': w.email,
                'submitted_at': sub.submitted_at.isoformat() if sub.submitted_at else None,
                'status': sub.status,
            })
        else:
            missing.append({
                'user_id': w.id,
                'user_name': w.display_name,
                'email': w.email,
                'draft_exists': sub is not None,
            })

    total = len(workers)
    return jsonify({
        'period_id': period_id,
        'period_name': period.name,
        'total_workers': total,
        'submitted_count': len(submitted),
        'missing_count': len(missing),
        'submission_rate': round(len(submitted) / total * 100, 1) if total else 0,
        'submitted': submitted,
        'missing': missing,
    })


@api_master_bp.route('/api/master/periods/<int:period_id>/submit-for-user', methods=['POST'])
@require_master
def submit_for_user(period_id):
    """Create a proxy submission on behalf of a worker (all unavailable)."""
    period = db.session.get(ShiftPeriod, period_id)
    if not period:
        return error_response("Period not found", 404)
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return error_response("user_id required", 400)
    user = db.session.get(User, user_id)
    if not user:
        return error_response("User not found", 404)

    existing = ShiftSubmission.query.filter_by(
        shift_period_id=period_id, user_id=user_id
    ).first()
    if existing and existing.status == 'submitted':
        return error_response("User already submitted", 400)

    if existing:
        submission = existing
    else:
        submission = ShiftSubmission(
            shift_period_id=period_id,
            user_id=user_id,
        )
        db.session.add(submission)

    submission.status = 'submitted'
    submission.submitted_at = datetime.utcnow()
    submission.notes = 'マスター管理者による代理提出（全日不可）'
    db.session.flush()

    # Create slots for each day in the period (all unavailable)
    from app.models.opening_hours import OpeningHours
    current = period.start_date
    while current <= period.end_date:
        existing_slot = ShiftSubmissionSlot.query.filter_by(
            submission_id=submission.id, slot_date=current
        ).first()
        if not existing_slot:
            slot = ShiftSubmissionSlot(
                submission_id=submission.id,
                slot_date=current,
                is_available=False,
            )
            db.session.add(slot)
        else:
            existing_slot.is_available = False
        current += timedelta(days=1)

    _log_master_action('MASTER_PROXY_SUBMISSION', 'ShiftSubmission', submission.id,
                       new_values={'user_id': user_id, 'period_id': period_id})
    db.session.commit()
    return jsonify({'ok': True, 'submission_id': submission.id})


# ===========================================================================
# Scenario 6: System health check & auto-fix
# ===========================================================================

@api_master_bp.route('/api/master/health-check')
@require_master
def health_check():
    """Run diagnostic checks and return issues found."""
    issues = {}

    # Role drift: User.role differs from OrganizationMember.role
    role_drift = (
        db.session.query(User.id, User.email, User.role, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(
            OrganizationMember.is_active == True,
            User.is_active == True,
            User.role != OrganizationMember.role,
        )
        .all()
    )
    issues['role_drift'] = {
        'count': len(role_drift),
        'items': [{'user_id': r[0], 'email': r[1], 'user_role': r[2], 'member_role': r[3]} for r in role_drift],
    }

    # Org ID drift: User.organization_id differs from membership
    org_drift = (
        db.session.query(User.id, User.email, User.organization_id, OrganizationMember.organization_id)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(
            OrganizationMember.is_active == True,
            User.is_active == True,
            User.organization_id != OrganizationMember.organization_id,
        )
        .all()
    )
    issues['org_id_drift'] = {
        'count': len(org_drift),
        'items': [{'user_id': r[0], 'email': r[1], 'user_org': r[2], 'member_org': r[3]} for r in org_drift],
    }

    # Stale memberships: active membership but inactive user
    stale = (
        db.session.query(OrganizationMember.id, User.email)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(
            OrganizationMember.is_active == True,
            User.is_active == False,
        )
        .all()
    )
    issues['stale_memberships'] = {
        'count': len(stale),
        'items': [{'member_id': r[0], 'email': r[1]} for r in stale],
    }

    # Orphaned users: have organization_id but no active membership
    orphaned = (
        db.session.query(User.id, User.email, User.organization_id)
        .outerjoin(
            OrganizationMember,
            db.and_(
                OrganizationMember.user_id == User.id,
                OrganizationMember.is_active == True,
            )
        )
        .filter(
            User.is_active == True,
            User.organization_id != None,
            OrganizationMember.id == None,
        )
        .all()
    )
    issues['orphaned_users'] = {
        'count': len(orphaned),
        'items': [{'user_id': r[0], 'email': r[1], 'org_id': r[2]} for r in orphaned],
    }

    # Expired invitations
    now = datetime.utcnow()
    expired_invites = InvitationToken.query.filter(
        InvitationToken.used_at == None,
        InvitationToken.expires_at < now,
    ).count()
    issues['expired_invitations'] = {'count': expired_invites}

    # Dead tasks
    dead_tasks = AsyncTask.query.filter(AsyncTask.status == 'dead').count()
    issues['dead_tasks'] = {'count': dead_tasks}

    # Unsynced confirmed entries
    unsynced = (
        db.session.query(func.count(ShiftScheduleEntry.id))
        .join(ShiftSchedule, ShiftSchedule.id == ShiftScheduleEntry.schedule_id)
        .filter(
            ShiftSchedule.status == 'confirmed',
            ShiftScheduleEntry.calendar_event_id == None,
        )
        .scalar()
    )
    issues['unsynced_entries'] = {'count': unsynced}

    # Total issues
    total = sum(v['count'] for v in issues.values())
    return jsonify({'total_issues': total, 'checks': issues})


@api_master_bp.route('/api/master/health-check/fix', methods=['POST'])
@require_master
def health_fix():
    """Apply a fix for a specific health issue category."""
    data = request.get_json(silent=True) or {}
    fix_type = data.get('fix_type')
    fixed = 0

    if fix_type == 'role_drift':
        members = OrganizationMember.query.filter_by(is_active=True).all()
        for m in members:
            user = db.session.get(User, m.user_id)
            if user and user.is_active and user.role != m.role:
                user.role = m.role
                user.organization_id = m.organization_id
                fixed += 1

    elif fix_type == 'org_id_drift':
        members = OrganizationMember.query.filter_by(is_active=True).all()
        for m in members:
            user = db.session.get(User, m.user_id)
            if user and user.is_active and user.organization_id != m.organization_id:
                user.organization_id = m.organization_id
                fixed += 1

    elif fix_type == 'stale_memberships':
        stale = (
            OrganizationMember.query
            .join(User, User.id == OrganizationMember.user_id)
            .filter(OrganizationMember.is_active == True, User.is_active == False)
            .all()
        )
        for m in stale:
            m.is_active = False
            fixed += 1

    elif fix_type == 'orphaned_users':
        from sqlalchemy import and_
        orphaned = (
            User.query
            .outerjoin(
                OrganizationMember,
                and_(
                    OrganizationMember.user_id == User.id,
                    OrganizationMember.is_active == True,
                )
            )
            .filter(
                User.is_active == True,
                User.organization_id != None,
                OrganizationMember.id == None,
            )
            .all()
        )
        for u in orphaned:
            u.organization_id = None
            u.role = 'worker'
            fixed += 1

    elif fix_type == 'expired_invitations':
        now = datetime.utcnow()
        expired = InvitationToken.query.filter(
            InvitationToken.used_at == None,
            InvitationToken.expires_at < now,
        ).all()
        for inv in expired:
            db.session.delete(inv)
            fixed += 1

    else:
        return error_response(f"Unknown fix_type: {fix_type}", 400)

    _log_master_action('MASTER_HEALTH_FIX', new_values={'fix_type': fix_type, 'fixed': fixed})
    db.session.commit()
    return jsonify({'ok': True, 'fix_type': fix_type, 'fixed': fixed})


# ---------------------------------------------------------------------------
# API: Audit logs
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/audit-logs')
@require_master
def list_audit_logs():
    """List audit logs across all organizations."""
    action = request.args.get('action')
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)
    logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    result = []
    for log in logs:
        actor = db.session.get(User, log.actor_id) if log.actor_id else None
        result.append({
            'id': log.id,
            'organization_id': log.organization_id,
            'actor_id': log.actor_id,
            'actor_email': actor.email if actor else None,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': log.resource_id,
            'old_values': log.old_values,
            'new_values': log.new_values,
            'ip_address': log.ip_address,
            'status': log.status,
            'error_message': log.error_message,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        })
    return jsonify(result)


# ---------------------------------------------------------------------------
# API: Danger zone — direct SQL (read-only)
# ---------------------------------------------------------------------------

@api_master_bp.route('/api/master/query', methods=['POST'])
@require_master
def run_query():
    """Execute a read-only SQL query. SELECT only."""
    data = request.get_json(silent=True) or {}
    sql = (data.get('sql') or '').strip()
    if not sql:
        return error_response("SQL query required", 400)

    normalized = sql.upper().lstrip()
    if not normalized.startswith('SELECT'):
        return error_response("Only SELECT queries are allowed", 400)

    dangerous = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'GRANT', 'REVOKE']
    for kw in dangerous:
        if kw in normalized:
            return error_response(f"Forbidden keyword: {kw}", 400)

    try:
        result = db.session.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return jsonify({'columns': columns, 'rows': rows, 'count': len(rows)})
    except Exception as e:
        return error_response(f"Query error: {str(e)}", 400)
