from datetime import datetime
from app.extensions import db
from app.models.shift import ShiftSchedule
from app.models.approval import ApprovalHistory
from app.models.user import User
from app.services.notification_service import notify_approval_requested, notify_approval_result


def submit_for_approval(schedule_id, admin_user):
    """Submit a schedule for owner approval."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or schedule.status != 'draft':
        return None, "Schedule not found or not in draft status"

    schedule.status = 'pending_approval'
    db.session.add(ApprovalHistory(
        schedule_id=schedule_id,
        action='submitted',
        performed_by=admin_user.id,
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, "Database error"

    # Notify owner
    period = schedule.period
    if period and period.organization:
        owner_email = period.organization.owner_email
        if owner_email:
            notify_approval_requested(owner_email, period.name, admin_user.display_name)

    return schedule, None


def approve_schedule(schedule_id, owner_user, comment=None):
    """Approve a schedule."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or schedule.status != 'pending_approval':
        return None, "Schedule not found or not pending approval"

    schedule.status = 'approved'
    schedule.approved_by = owner_user.id
    schedule.approved_at = datetime.utcnow()

    db.session.add(ApprovalHistory(
        schedule_id=schedule_id,
        action='approved',
        performed_by=owner_user.id,
        comment=comment,
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, "Database error"

    # Notify admin
    creator = db.session.get(User, schedule.created_by)
    if creator:
        period = schedule.period
        notify_approval_result(creator.email, period.name if period else '', 'approved', comment)

    return schedule, None


def reject_schedule(schedule_id, owner_user, comment=None):
    """Reject (send back) a schedule."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or schedule.status != 'pending_approval':
        return None, "Schedule not found or not pending approval"

    schedule.status = 'rejected'
    schedule.rejection_reason = comment

    db.session.add(ApprovalHistory(
        schedule_id=schedule_id,
        action='rejected',
        performed_by=owner_user.id,
        comment=comment,
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, "Database error"

    # Notify admin
    creator = db.session.get(User, schedule.created_by)
    if creator:
        period = schedule.period
        notify_approval_result(creator.email, period.name if period else '', 'rejected', comment)

    return schedule, None


def confirm_schedule(schedule_id, admin_user):
    """Confirm an approved schedule (ready for calendar sync)."""
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or schedule.status != 'approved':
        return None, "Schedule not found or not approved"

    schedule.status = 'confirmed'
    schedule.confirmed_at = datetime.utcnow()

    db.session.add(ApprovalHistory(
        schedule_id=schedule_id,
        action='confirmed',
        performed_by=admin_user.id,
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None, "Database error"

    return schedule, None
