import logging

from flask import current_app, session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.extensions import db
from app.models.user import User, UserToken

auth_svc_logger = logging.getLogger('auth')


def get_client_config():
    """Build Google OAuth client config from app settings."""
    return {
        "web": {
            "client_id": current_app.config['GOOGLE_CLIENT_ID'],
            "client_secret": current_app.config['GOOGLE_CLIENT_SECRET'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [current_app.config['GOOGLE_REDIRECT_URI']]
        }
    }


def create_oauth_flow(state=None):
    """Create a Google OAuth flow."""
    scopes = current_app.config['GOOGLE_SCOPES_WRITE']
    flow = Flow.from_client_config(
        get_client_config(),
        scopes=scopes,
        state=state,
        redirect_uri=current_app.config['GOOGLE_REDIRECT_URI']
    )
    return flow


def extract_user_info(credentials):
    """Extract user info from OAuth credentials."""
    client_id = current_app.config['GOOGLE_CLIENT_ID']

    # Try id_token first
    if credentials.id_token:
        token_data = credentials.id_token

        # Already decoded (dict) — use directly
        if isinstance(token_data, dict):
            current_app.logger.info(f"id_token is dict, sub={token_data.get('sub')}")
            return token_data.get('sub'), token_data.get('email'), token_data.get('name')

        # JWT string — verify and decode
        try:
            decoded = id_token.verify_oauth2_token(
                token_data, google_requests.Request(), client_id
            )
            current_app.logger.info(f"id_token verified, sub={decoded.get('sub')}")
            return decoded.get('sub'), decoded.get('email'), decoded.get('name')
        except Exception as e:
            current_app.logger.warning(f"id_token verification failed: {e}")

    # Fallback: use userinfo API
    try:
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        current_app.logger.info(f"userinfo API: id={user_info.get('id')}")
        return user_info.get('id'), user_info.get('email'), user_info.get('name')
    except Exception as e:
        current_app.logger.error(f"userinfo API failed: {e}")
        return None, None, None


def determine_role(email):
    """Determine user role from DB membership, falling back to env config for bootstrap.

    Priority:
    1. Existing OrganizationMember record → that role
    2. ADMIN_EMAIL / OWNER_EMAIL env vars → for initial bootstrap only
    3. Default → 'worker'
    """
    from app.models.membership import OrganizationMember

    # Check existing membership first
    user = User.query.filter_by(email=email).first()
    if user:
        membership = OrganizationMember.query.filter_by(
            user_id=user.id, is_active=True
        ).first()
        if membership:
            return membership.role

    # Fallback to env config (bootstrap)
    admin_emails = [e.strip() for e in current_app.config.get('ADMIN_EMAIL', '').split(',') if e.strip()]
    owner_emails = [e.strip() for e in current_app.config.get('OWNER_EMAIL', '').split(',') if e.strip()]

    if email in admin_emails:
        return 'admin'
    if email in owner_emails:
        return 'owner'
    return 'worker'


def upsert_user(google_id, email, display_name, invitation_token=None):
    """Create or update a user record.

    If *invitation_token* is provided (an InvitationToken instance),
    the user is assigned to the token's org with the token's role.
    Otherwise, existing membership is preserved or env-config bootstrap applies.
    """
    from app.models.organization import Organization
    from app.models.membership import OrganizationMember, InvitationToken

    user = User.query.filter_by(google_id=google_id).first()
    role = determine_role(email)

    if user:
        if user.role != role:
            auth_svc_logger.warning(
                "ROLE_CHANGE: user_id=%s email=%s old_role=%s new_role=%s",
                user.id, email, user.role, role,
            )
        user.email = email
        user.display_name = display_name
        user.role = role
    else:
        user = User(
            google_id=google_id,
            email=email,
            display_name=display_name,
            role=role,
        )
        db.session.add(user)
        db.session.flush()  # get user.id

    # --- Org / membership assignment ---
    if invitation_token and invitation_token.is_valid:
        # Invitation-based assignment
        _accept_invitation(user, invitation_token)
    elif not user.organization_id:
        # Bootstrap: only auto-assign for env-configured admin/owner emails
        admin_emails = [e.strip() for e in current_app.config.get('ADMIN_EMAIL', '').split(',') if e.strip()]
        owner_emails = [e.strip() for e in current_app.config.get('OWNER_EMAIL', '').split(',') if e.strip()]
        if email in admin_emails or email in owner_emails:
            org = Organization.query.first()
            if org:
                user.organization_id = org.id
                user.role = role
                _ensure_membership(user, org.id, role)
        # Otherwise: user remains without organization (must be invited)

    # Sync role from membership (authoritative source)
    membership = OrganizationMember.query.filter_by(
        user_id=user.id, is_active=True
    ).first()
    if membership:
        user.role = membership.role
        user.organization_id = membership.organization_id

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user


def _accept_invitation(user, token):
    """Accept an invitation token: assign user to org with the specified role."""
    from app.models.membership import OrganizationMember
    from datetime import datetime

    membership = OrganizationMember.query.filter_by(
        user_id=user.id, organization_id=token.organization_id
    ).first()

    if membership:
        membership.role = token.role
        membership.is_active = True
    else:
        membership = OrganizationMember(
            user_id=user.id,
            organization_id=token.organization_id,
            role=token.role,
            invited_by=token.created_by,
        )
        db.session.add(membership)

    user.organization_id = token.organization_id
    user.role = token.role

    # Mark token as used
    token.used_at = datetime.utcnow()
    token.used_by = user.id


def _ensure_membership(user, org_id, role):
    """Create an OrganizationMember record if one doesn't exist."""
    from app.models.membership import OrganizationMember

    existing = OrganizationMember.query.filter_by(
        user_id=user.id, organization_id=org_id
    ).first()
    if not existing:
        db.session.add(OrganizationMember(
            user_id=user.id,
            organization_id=org_id,
            role=role,
        ))
    elif not existing.is_active:
        existing.is_active = True
        existing.role = role


def save_refresh_token(user, refresh_token, scopes=None):
    """Save or update a user's refresh token (encrypted)."""
    from app.utils.crypto import encrypt_token

    encrypted = encrypt_token(refresh_token)
    token = UserToken.query.filter_by(user_id=user.id).first()
    if token:
        token.refresh_token = encrypted
        if scopes:
            token.scopes = ','.join(scopes) if isinstance(scopes, (list, set)) else scopes
    else:
        token = UserToken(
            user_id=user.id,
            refresh_token=encrypted,
            scopes=','.join(scopes) if isinstance(scopes, (list, set)) else scopes,
        )
        db.session.add(token)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _decrypt_refresh_token(token_record):
    """Decrypt refresh token with transparent migration for plaintext tokens."""
    from app.utils.crypto import decrypt_token, encrypt_token

    stored = token_record.refresh_token
    if not stored:
        return None

    # Try to decrypt (encrypted token)
    plaintext = decrypt_token(stored)
    if plaintext is not None:
        return plaintext

    # Decryption failed — assume it's a plaintext token (legacy), migrate it
    auth_svc_logger.info(
        "Migrating plaintext refresh token for user_id=%s to encrypted",
        token_record.user_id,
    )
    token_record.refresh_token = encrypt_token(stored)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return stored


def get_credentials_for_user(user):
    """Build Google Credentials for a user, refreshing if needed."""
    token = UserToken.query.filter_by(user_id=user.id).first()
    if not token:
        return None

    refresh_token = _decrypt_refresh_token(token)
    session_creds = session.get('credentials', {})

    creds_data = {
        'token': session_creds.get('token'),
        'refresh_token': refresh_token,
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': current_app.config['GOOGLE_CLIENT_ID'],
        'client_secret': current_app.config['GOOGLE_CLIENT_SECRET'],
        'scopes': current_app.config['GOOGLE_SCOPES_WRITE'],
    }

    credentials = Credentials(**creds_data)

    if not credentials.valid:
        try:
            credentials.refresh(Request())
            session['credentials'] = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to refresh access token: {e}")

    return credentials
