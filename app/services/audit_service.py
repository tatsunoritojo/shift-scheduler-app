"""Audit logging service for security-sensitive operations."""

import logging

from flask import request
from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log_audit(
    action,
    resource_type,
    resource_id=None,
    actor_id=None,
    organization_id=None,
    old_values=None,
    new_values=None,
    status='SUCCESS',
    error_message=None,
):
    """Record an audit log entry.

    Best-effort: failures are logged but never raised to callers.
    """
    try:
        ip_address = request.remote_addr if request else None
    except RuntimeError:
        ip_address = None

    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        status=status,
        error_message=error_message,
    )
    try:
        db.session.add(entry)
        # Don't commit here — let the caller's transaction handle it.
        # If the caller rolls back, the audit entry rolls back too, which is fine
        # (failed operations shouldn't leave audit entries).
        db.session.flush()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)
