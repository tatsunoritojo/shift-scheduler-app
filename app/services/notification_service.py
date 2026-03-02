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


def notify_submission_deadline(to_email, worker_name, period_name, deadline_str,
                               submit_url, *, organization_id=None, created_by=None):
    """Notify a worker that the submission deadline is approaching (async)."""
    safe_name = html_escape(worker_name)
    safe_period = html_escape(period_name)
    safe_deadline = html_escape(deadline_str)
    safe_url = html_escape(submit_url)
    subject = f"[シフリー] 提出期限リマインド: {period_name}"
    body = f"""
    <h3>シフト希望の提出期限が近づいています</h3>
    <p>{safe_name} さん、シフト期間「{safe_period}」の希望提出期限が近づいています。</p>
    <p>提出期限: <strong>{safe_deadline}</strong></p>
    <p><a href="{safe_url}" style="display:inline-block;padding:12px 24px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">シフト希望を提出する</a></p>
    """
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_preshift(to_email, worker_name, shift_date_str, start_time, end_time,
                    *, organization_id=None, created_by=None):
    """Notify a worker about an upcoming shift (async)."""
    safe_name = html_escape(worker_name)
    safe_date = html_escape(shift_date_str)
    safe_start = html_escape(start_time)
    safe_end = html_escape(end_time)
    subject = f"[シフリー] シフトリマインド: {shift_date_str}"
    body = f"""
    <h3>明日のシフトのお知らせ</h3>
    <p>{safe_name} さん、明日のシフト予定をお知らせします。</p>
    <p>日付: <strong>{safe_date}</strong></p>
    <p>時間: <strong>{safe_start} 〜 {safe_end}</strong></p>
    <p>遅刻・欠勤の場合は早めにご連絡ください。</p>
    """
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_vacancy_request(to_email, user_name, shift_date, start_time, end_time,
                           reason, accept_url, decline_url,
                           *, organization_id=None, created_by=None):
    """Notify a candidate about a vacancy fill request (async)."""
    safe_name = html_escape(user_name)
    safe_date = html_escape(str(shift_date))
    safe_start = html_escape(start_time)
    safe_end = html_escape(end_time)
    safe_reason = html_escape(reason) if reason else ''
    safe_accept = html_escape(accept_url)
    safe_decline = html_escape(decline_url)
    subject = f"[シフリー] 欠員補充のお願い: {shift_date}"
    body = f"""
    <h3>シフトの欠員補充のお願い</h3>
    <p>{safe_name} さん、以下のシフトに欠員が発生しました。代わりに出勤いただけないでしょうか？</p>
    <p>日付: <strong>{safe_date}</strong></p>
    <p>時間: <strong>{safe_start} 〜 {safe_end}</strong></p>
    """
    if safe_reason:
        body += f"<p>理由: {safe_reason}</p>"
    body += f"""
    <p>
        <a href="{safe_accept}" style="display:inline-block;padding:12px 24px;background:#22c55e;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;margin-right:12px;">引き受ける</a>
        <a href="{safe_decline}" style="display:inline-block;padding:12px 24px;background:#6b7280;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">辞退する</a>
    </p>
    <p style="color:#999;font-size:0.85em;">このリンクは本人専用です。他の方と共有しないでください。</p>
    """
    return _enqueue_or_send(to_email, subject, body,
                            organization_id=organization_id, created_by=created_by)


def notify_vacancy_accepted(admin_email, shift_date, start_time, end_time,
                            original_name, new_name,
                            *, organization_id=None, created_by=None):
    """Notify admin that a vacancy has been filled (async)."""
    safe_date = html_escape(str(shift_date))
    safe_start = html_escape(start_time)
    safe_end = html_escape(end_time)
    safe_orig = html_escape(original_name)
    safe_new = html_escape(new_name)
    subject = f"[シフリー] 欠員補充完了: {shift_date}"
    body = f"""
    <h3>欠員補充が完了しました</h3>
    <p>以下のシフトの欠員補充が完了しました。</p>
    <p>日付: <strong>{safe_date}</strong></p>
    <p>時間: <strong>{safe_start} 〜 {safe_end}</strong></p>
    <p>変更前: {safe_orig} → 変更後: <strong>{safe_new}</strong></p>
    """
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
