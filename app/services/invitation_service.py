import logging
import secrets
from datetime import datetime, timedelta
from html import escape as html_escape

from flask import current_app

from app.extensions import db
from app.models.invitation import Invitation
from app.models.organization import Organization
from app.models.user import User
from app.services.notification_service import send_email, _sanitize_subject

invitation_logger = logging.getLogger('invitation')

INVITE_EXPIRY_DAYS = 7


def create_email_invitation(org_id, email, admin_user):
    """Create an email invitation. Returns (Invitation, error_string)."""
    email = email.strip().lower()

    # Check for duplicate pending invitation
    existing = Invitation.query.filter_by(
        organization_id=org_id, email=email, status='pending'
    ).first()
    if existing:
        return None, 'この宛先には既に保留中の招待があります'

    # Check if already a member
    existing_user = User.query.filter_by(email=email, organization_id=org_id).first()
    if existing_user:
        return None, 'このメールアドレスは既にメンバーです'

    org = db.session.get(Organization, org_id)
    if not org:
        return None, '組織が見つかりません'

    invitation = Invitation(
        organization_id=org_id,
        email=email,
        invite_type='email',
        token=Invitation.generate_token(),
        status='pending',
        invited_by=admin_user.id,
        expires_at=datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.session.add(invitation)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _send_invitation_email(invitation, org, admin_user)

    invitation_logger.info(
        "INVITE_CREATED: org=%s email=%s by=%s",
        org_id, email, admin_user.id,
    )
    return invitation, None


def create_or_get_invite_code(org_id, admin_user):
    """Return the org's invite code, generating one if it doesn't exist."""
    org = db.session.get(Organization, org_id)
    if not org:
        return None, '組織が見つかりません'

    if not org.invite_code:
        org.invite_code = secrets.token_urlsafe(16)
        org.invite_code_created_at = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return org.invite_code, None


def regenerate_invite_code(org_id, admin_user):
    """Regenerate the org's invite code (old one becomes invalid)."""
    org = db.session.get(Organization, org_id)
    if not org:
        return None, '組織が見つかりません'

    org.invite_code = secrets.token_urlsafe(16)
    org.invite_code_created_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    invitation_logger.info(
        "INVITE_CODE_REGENERATED: org=%s by=%s", org_id, admin_user.id,
    )
    return org.invite_code, None


def validate_and_accept_invitation(token, user):
    """Validate a token-based invitation and accept it. Returns (org_id, error)."""
    invitation = Invitation.query.filter_by(token=token, status='pending').first()
    if not invitation:
        return None, '無効な招待です'

    if invitation.is_expired:
        invitation.status = 'expired'
        db.session.commit()
        return None, '招待の有効期限が切れています'

    # For email invitations, verify the email matches
    if invitation.invite_type == 'email' and invitation.email:
        if invitation.email.lower() != user.email.lower():
            return None, 'この招待は別のメールアドレス宛です'

    invitation.status = 'accepted'
    invitation.accepted_by = user.id
    invitation.accepted_at = datetime.utcnow()
    if not invitation.email:
        invitation.email = user.email

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    invitation_logger.info(
        "INVITE_ACCEPTED: invitation=%s user=%s org=%s",
        invitation.id, user.id, invitation.organization_id,
    )
    return invitation.organization_id, None


def check_email_invitation(email):
    """Check if there's a pending email invitation for this email. Returns org_id or None."""
    invitation = Invitation.query.filter_by(
        email=email.lower(), invite_type='email', status='pending'
    ).first()
    if not invitation:
        return None

    if invitation.is_expired:
        invitation.status = 'expired'
        db.session.commit()
        return None

    return invitation


def accept_email_invitation(invitation, user):
    """Accept a found email invitation."""
    invitation.status = 'accepted'
    invitation.accepted_by = user.id
    invitation.accepted_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return invitation.organization_id


def resolve_invite_code(code):
    """Find org by invite code. Returns (org, error)."""
    org = Organization.query.filter_by(invite_code=code).first()
    if not org:
        return None, '無効な招待コードです'
    return org, None


def cancel_invitation(invitation_id, admin_user):
    """Cancel a pending invitation."""
    invitation = db.session.get(Invitation, invitation_id)
    if not invitation:
        return None, '招待が見つかりません'
    if invitation.status != 'pending':
        return None, 'この招待は既に処理済みです'

    invitation.status = 'cancelled'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    invitation_logger.info(
        "INVITE_CANCELLED: invitation=%s by=%s", invitation_id, admin_user.id,
    )
    return invitation, None


def toggle_member_active(user_id, is_active, admin_user):
    """Toggle a member's active status. Returns (user, error)."""
    user = db.session.get(User, user_id)
    if not user:
        return None, 'ユーザーが見つかりません'

    if user.role in ('admin', 'owner'):
        return None, '管理者・オーナーは無効化できません'

    if user.organization_id != admin_user.organization_id:
        return None, '別の組織のメンバーです'

    user.is_active = is_active
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    invitation_logger.info(
        "MEMBER_ACTIVE_TOGGLE: user=%s is_active=%s by=%s",
        user_id, is_active, admin_user.id,
    )
    return user, None


def list_members(org_id):
    """List all members in an organization."""
    users = User.query.filter_by(organization_id=org_id).order_by(
        User.role, User.display_name
    ).all()
    return [{
        'id': u.id,
        'email': u.email,
        'display_name': u.display_name,
        'role': u.role,
        'is_active': u.is_active,
        'created_at': u.created_at.isoformat() if u.created_at else None,
    } for u in users]


def list_invitations(org_id, status=None):
    """List invitations for an organization."""
    query = Invitation.query.filter_by(organization_id=org_id)
    if status:
        query = query.filter_by(status=status)
    invitations = query.order_by(Invitation.created_at.desc()).all()
    return [inv.to_dict() for inv in invitations]


def get_invitation_info(token=None, code=None):
    """Get public info about an invitation for the landing page."""
    if token:
        invitation = Invitation.query.filter_by(token=token, status='pending').first()
        if not invitation:
            return None, '無効な招待です'
        if invitation.is_expired:
            invitation.status = 'expired'
            db.session.commit()
            return None, '招待の有効期限が切れています'
        org = db.session.get(Organization, invitation.organization_id)
        return {
            'organization_name': org.name if org else '不明',
            'invite_type': 'email',
            'login_url': f'/auth/google/login?invite={token}',
        }, None

    if code:
        org = Organization.query.filter_by(invite_code=code).first()
        if not org:
            return None, '無効な招待コードです'
        return {
            'organization_name': org.name,
            'invite_type': 'link',
            'login_url': f'/auth/google/login?invite_code={code}',
        }, None

    return None, 'トークンまたはコードが必要です'


def _send_invitation_email(invitation, org, admin_user):
    """Send invitation email to the invitee."""
    safe_org = html_escape(org.name)
    safe_admin = html_escape(admin_user.display_name or admin_user.email)
    invite_url = f'/invite?token={invitation.token}'

    subject = _sanitize_subject(f'[シフリー] {org.name} への招待')
    body = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:480px;margin:0 auto;">
        <h2 style="color:#1e293b;">シフリーへの招待</h2>
        <p>{safe_admin} さんから <strong>{safe_org}</strong> への招待が届いています。</p>
        <p style="margin:24px 0;">
            <a href="{html_escape(invite_url)}"
               style="display:inline-block;padding:14px 32px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">
                招待を受け入れる
            </a>
        </p>
        <p style="color:#64748b;font-size:0.9em;">この招待は {INVITE_EXPIRY_DAYS} 日間有効です。</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
        <p style="color:#94a3b8;font-size:0.82em;">シフリー - Googleカレンダー連携シフト管理</p>
    </div>
    """
    send_email(invitation.email, subject, body)
