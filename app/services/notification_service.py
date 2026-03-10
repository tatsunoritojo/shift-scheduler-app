"""Notification service — email delivery with async queue support.

Public functions (notify_*) enqueue tasks by default for background
delivery.  The ``send_email`` function does synchronous SMTP and is
called by the task runner when processing queued emails.
"""

import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import render_template

logger = logging.getLogger(__name__)


def _sanitize_subject(subject):
    """Remove characters that could be used for SMTP header injection."""
    if not subject:
        return subject
    return subject.replace('\r', '').replace('\n', '').replace('\x00', '')


# ---------------------------------------------------------------------------
# Low-level synchronous email send (used by task runner)
# ---------------------------------------------------------------------------

def send_email(to_email, subject, body_html):
    """Send an email notification synchronously. Returns True on success."""
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    from_email = os.environ.get('SMTP_FROM', smtp_user)

    if not smtp_host or not smtp_user:
        logger.info("SMTP not configured. Skipping email to %s: %s", to_email, subject)
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = _sanitize_subject(subject)
        msg['From'] = from_email
        msg['To'] = to_email
        msg.attach(MIMEText(body_html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False


# ---------------------------------------------------------------------------
# Public API — enqueue notifications for async delivery
# ---------------------------------------------------------------------------

def notify_approval_requested(owner_email, period_name, admin_name,
                              *, organization_id=None, created_by=None):
    """Notify owner that a schedule needs approval (async)."""
    subject = f"[シフリー] 承認依頼: {period_name}"
    body = render_template('emails/approval_requested.html',
                           period_name=period_name, admin_name=admin_name)
    return _enqueue_or_send(owner_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_approval_result(admin_email, period_name, action, comment=None,
                           *, organization_id=None, created_by=None):
    """Notify admin of approval/rejection result (async)."""
    action_text = '承認' if action == 'approved' else '差戻し'
    subject = f"[シフリー] {action_text}: {period_name}"
    body = render_template('emails/approval_result.html',
                           period_name=period_name, action_text=action_text,
                           comment=comment)
    return _enqueue_or_send(admin_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_invitation_created(to_email, org_name, inviter_name, role, invite_url,
                               expires_at, *, organization_id=None, created_by=None):
    """Notify a user that they have been invited to an organization (async)."""
    role_ja = {'admin': '管理者', 'owner': '事業主', 'worker': 'アルバイト'}.get(role, role)
    expires_str = expires_at.strftime('%Y/%m/%d %H:%M') if expires_at else ''

    subject = f"[シフリー] {org_name} への招待"
    body = render_template('emails/invitation_created.html',
                           org_name=org_name, inviter_name=inviter_name,
                           role_ja=role_ja, invite_url=invite_url,
                           expires_str=expires_str)
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_submission_deadline(to_email, worker_name, period_name, deadline_str,
                               submit_url, *, organization_id=None, created_by=None):
    """Notify a worker that the submission deadline is approaching (async)."""
    subject = f"[シフリー] 提出期限リマインド: {period_name}"
    body = render_template('emails/submission_deadline.html',
                           worker_name=worker_name, period_name=period_name,
                           deadline_str=deadline_str, submit_url=submit_url)
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_preshift(to_email, worker_name, shift_date_str, start_time, end_time,
                    *, organization_id=None, created_by=None):
    """Notify a worker about an upcoming shift (async)."""
    subject = f"[シフリー] シフトリマインド: {shift_date_str}"
    body = render_template('emails/preshift.html',
                           worker_name=worker_name, shift_date_str=shift_date_str,
                           start_time=start_time, end_time=end_time)
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_vacancy_request(to_email, user_name, shift_date, start_time, end_time,
                           reason, accept_url, decline_url,
                           *, organization_id=None, created_by=None):
    """Notify a candidate about a vacancy fill request (async)."""
    subject = f"[シフリー] 欠員補充のお願い: {shift_date}"
    body = render_template('emails/vacancy_request.html',
                           user_name=user_name, shift_date=str(shift_date),
                           start_time=start_time, end_time=end_time,
                           reason=reason, accept_url=accept_url,
                           decline_url=decline_url)
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_vacancy_accepted(admin_email, shift_date, start_time, end_time,
                            original_name, new_name,
                            *, organization_id=None, created_by=None):
    """Notify admin that a vacancy has been filled (async)."""
    subject = f"[シフリー] 欠員補充完了: {shift_date}"
    body = render_template('emails/vacancy_accepted.html',
                           shift_date=str(shift_date), start_time=start_time,
                           end_time=end_time, original_name=original_name,
                           new_name=new_name)
    return _enqueue_or_send(admin_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


# ---------------------------------------------------------------------------
# Internal — enqueue with sync fallback
# ---------------------------------------------------------------------------

def _enqueue_or_send(to_email, subject, body_html, *, organization_id=None, created_by=None):
    """Try to enqueue; fall back to synchronous send on import/DB errors."""
    try:
        from app.services.task_runner import enqueue_email
        from app.extensions import db
        enqueue_email(
            to_email, subject, body_html,
            organization_id=organization_id,
            created_by=created_by,
        )
        db.session.commit()
        return True
    except Exception:
        logger.debug("Async enqueue failed, falling back to sync send", exc_info=True)
        return send_email(to_email, subject, body_html)
