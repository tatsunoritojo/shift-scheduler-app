import smtplib
import os
from html import escape as html_escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def _sanitize_subject(subject):
    """Remove characters that could be used for SMTP header injection."""
    if not subject:
        return subject
    return subject.replace('\r', '').replace('\n', '').replace('\x00', '')


def send_email(to_email, subject, body_html):
    """Send an email notification. Silently fails if SMTP not configured."""
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    from_email = os.environ.get('SMTP_FROM', smtp_user)

    if not smtp_host or not smtp_user:
        current_app.logger.info(f"SMTP not configured. Skipping email to {to_email}: {subject}")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        msg.attach(MIMEText(body_html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        current_app.logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def notify_approval_requested(owner_email, period_name, admin_name):
    """Notify owner that a schedule needs approval."""
    safe_period = html_escape(period_name)
    safe_admin = html_escape(admin_name)
    subject = _sanitize_subject(f"[シフリー] 承認依頼: {period_name}")
    body = f"""
    <h3>シフトスケジュールの承認依頼</h3>
    <p>{safe_admin} さんがシフトスケジュール「{safe_period}」の承認を依頼しています。</p>
    <p>システムにログインして確認してください。</p>
    """
    return send_email(owner_email, subject, body)


def notify_approval_result(admin_email, period_name, action, comment=None):
    """Notify admin of approval/rejection result."""
    safe_period = html_escape(period_name)
    action_text = '承認' if action == 'approved' else '差戻し'
    subject = _sanitize_subject(f"[シフリー] {action_text}: {period_name}")
    body = f"""
    <h3>シフトスケジュールが{action_text}されました</h3>
    <p>シフトスケジュール「{safe_period}」が{action_text}されました。</p>
    """
    if comment:
        body += f"<p>コメント: {html_escape(comment)}</p>"
    return send_email(admin_email, subject, body)
