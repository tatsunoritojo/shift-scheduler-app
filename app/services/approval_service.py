from datetime import datetime
from app.extensions import db
from app.models.shift import ShiftSchedule
from app.models.approval import ApprovalHistory
from app.models.user import User
from app.services.notification_service import notify_approval_requested, notify_approval_result
from app.services.audit_service import log_audit


def _try_commit():
    """Best-effort commit for post-rollback audit entries."""
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _transition_schedule(
    schedule_id,
    actor,
    *,
    expected_status,
    new_status,
    action_name,
    audit_action,
    schedule_updates=None,
    history_fields=None,
    audit_new_values=None,
):
    """Apply a status transition with audit logging and safe commit/rollback.

    Args:
        schedule_id: ID of the ShiftSchedule to transition.
        actor: The User performing the action.
        expected_status: The status the schedule must currently have.
        new_status: The status to set on the schedule.
        action_name: Error-message fragment describing the expected state
            (e.g. "not in draft status", "not pending approval").
        audit_action: The action string for log_audit (e.g. 'SCHEDULE_APPROVED').
        schedule_updates: Optional dict of extra attributes to set on the
            schedule object (e.g. {'approved_by': user.id}).
        history_fields: Optional dict of extra fields for the ApprovalHistory
            row (e.g. {'comment': '...'}).
        audit_new_values: Optional dict merged into the audit new_values.

    Returns:
        (schedule, None) on success, or (None, error_message) on failure.
    """
    schedule = db.session.get(ShiftSchedule, schedule_id)
    if not schedule or schedule.status != expected_status:
        return None, f"Schedule not found or {action_name}"

    # Step 2: Update schedule status + any extra fields
    schedule.status = new_status
    if schedule_updates:
        for attr, value in schedule_updates.items():
            setattr(schedule, attr, value)

    # Step 3: Add ApprovalHistory
    history_kwargs = {
        'schedule_id': schedule_id,
        'action': new_status if new_status != 'pending_approval' else 'submitted',
        'performed_by': actor.id,
    }
    if history_fields:
        history_kwargs.update(history_fields)
    db.session.add(ApprovalHistory(**history_kwargs))

    # Step 4: Audit (success)
    org_id = schedule.period.organization_id if schedule.period else None
    new_values = {'status': new_status}
    if audit_new_values:
        new_values.update(audit_new_values)
    log_audit(
        action=audit_action,
        resource_type='ShiftSchedule',
        resource_id=schedule_id,
        actor_id=actor.id,
        organization_id=org_id,
        new_values=new_values,
    )

    # Step 5: Commit or rollback + failure audit
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_audit(
            action=audit_action,
            resource_type='ShiftSchedule',
            resource_id=schedule_id,
            actor_id=actor.id,
            organization_id=org_id,
            status='FAILED',
            error_message=str(e),
        )
        _try_commit()
        return None, "Database error"

    return schedule, None


def submit_for_approval(schedule_id, admin_user):
    """Submit a schedule for owner approval."""
    schedule, error = _transition_schedule(
        schedule_id,
        admin_user,
        expected_status='draft',
        new_status='pending_approval',
        action_name='not in draft status',
        audit_action='SCHEDULE_SUBMITTED',
    )
    if error:
        return None, error

    # Notify owner
    period = schedule.period
    if period and period.organization:
        owner_email = period.organization.owner_email
        if owner_email:
            notify_approval_requested(owner_email, period.name, admin_user.display_name)

    return schedule, None


def approve_schedule(schedule_id, owner_user, comment=None):
    """Approve a schedule."""
    schedule, error = _transition_schedule(
        schedule_id,
        owner_user,
        expected_status='pending_approval',
        new_status='approved',
        action_name='not pending approval',
        audit_action='SCHEDULE_APPROVED',
        schedule_updates={
            'approved_by': owner_user.id,
            'approved_at': datetime.utcnow(),
        },
        history_fields={'comment': comment},
        audit_new_values={'comment': comment},
    )
    if error:
        return None, error

    # Notify admin
    creator = db.session.get(User, schedule.created_by)
    if creator:
        period = schedule.period
        notify_approval_result(creator.email, period.name if period else '', 'approved', comment)

    return schedule, None


def reject_schedule(schedule_id, owner_user, comment=None):
    """Reject (send back) a schedule."""
    schedule, error = _transition_schedule(
        schedule_id,
        owner_user,
        expected_status='pending_approval',
        new_status='rejected',
        action_name='not pending approval',
        audit_action='SCHEDULE_REJECTED',
        schedule_updates={'rejection_reason': comment},
        history_fields={'comment': comment},
        audit_new_values={'comment': comment},
    )
    if error:
        return None, error

    # Notify admin
    creator = db.session.get(User, schedule.created_by)
    if creator:
        period = schedule.period
        notify_approval_result(creator.email, period.name if period else '', 'rejected', comment)

    return schedule, None


def confirm_schedule(schedule_id, admin_user):
    """Confirm an approved schedule (ready for calendar sync)."""
    schedule, error = _transition_schedule(
        schedule_id,
        admin_user,
        expected_status='approved',
        new_status='confirmed',
        action_name='not approved',
        audit_action='SCHEDULE_CONFIRMED',
        schedule_updates={'confirmed_at': datetime.utcnow()},
    )
    if error:
        return None, error

    return schedule, None
