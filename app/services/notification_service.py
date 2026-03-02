"""Notification service — email delivery with async queue support.

Public functions (notify_*) enqueue tasks by default for background
delivery.  The ``send_email`` function does synchronous SMTP and is
called by the task runner when processing queued emails.
"""

import logging
import smtplib
import os
from html import escape as html_escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    safe_period = html_escape(period_name)
    safe_admin = html_escape(admin_name)
    subject = f"[シフリー] 承認依頼: {period_name}"
    body = f"""
    <h3>シフトスケジュールの承認依頼</h3>
    <p>{safe_admin} さんがシフトスケジュール「{safe_period}」の承認を依頼しています。</p>
    <p>システムにログインして確認してください。</p>
    """
    return _enqueue_or_send(owner_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_approval_result(admin_email, period_name, action, comment=None,
                           *, organization_id=None, created_by=None):
    """Notify admin of approval/rejection result (async)."""
    safe_period = html_escape(period_name)
    action_text = '承認' if action == 'approved' else '差戻し'
    subject = f"[シフリー] {action_text}: {period_name}"
    body = f"""
    <h3>シフトスケジュールが{action_text}されました</h3>
    <p>シフトスケジュール「{safe_period}」が{action_text}されました。</p>
    """
    if comment:
        body += f"<p>コメント: {html_escape(comment)}</p>"
    return _enqueue_or_send(admin_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_invitation_created(to_email, org_name, inviter_name, role, invite_url,
                               expires_at, *, organization_id=None, created_by=None):
    """Notify a user that they have been invited to an organization (async)."""
    safe_org = html_escape(org_name)
    safe_inviter = html_escape(inviter_name)
    role_ja = {'admin': '管理者', 'owner': '事業主', 'worker': 'アルバイト'}.get(role, role)
    safe_url = html_escape(invite_url)
    expires_str = expires_at.strftime('%Y/%m/%d %H:%M') if expires_at else ''

    subject = f"[シフリー] {safe_org} への招待"
    body = f"""
    <h3>{safe_org} への招待</h3>
    <p>{safe_inviter} さんがあなたを「{safe_org}」に{role_ja}として招待しました。</p>
    <p>以下のリンクをクリックして参加してください:</p>
    <p><a href="{safe_url}" style="display:inline-block;padding:12px 24px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">招待を受ける</a></p>
    <p style="color:#999;font-size:0.85em;">このリンクの有効期限: {expires_str}</p>
    """
    return _enqueue_or_send(to_email, subject, body,
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
