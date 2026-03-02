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
    """Determine user role based on email and config."""
    admin_emails = [e.strip() for e in current_app.config.get('ADMIN_EMAIL', '').split(',') if e.strip()]
    owner_emails = [e.strip() for e in current_app.config.get('OWNER_EMAIL', '').split(',') if e.strip()]

    if email in admin_emails:
        return 'admin'
    if email in owner_emails:
        return 'owner'
    return 'worker'


def upsert_user(google_id, email, display_name, invite_token=None, invite_code=None):
    """Create or update a user record.

    Returns the User on success, or None if access is denied (inactive).

    New user flow:
      - With invitation (token/code/email match) → join that org as worker
      - Without invitation → create a new organization as admin
    """
    from app.models.organization import Organization
    from app.services.invitation_service import (
        validate_and_accept_invitation, resolve_invite_code,
        check_email_invitation, accept_email_invitation,
    )

    user = User.query.filter_by(google_id=google_id).first()

    if user:
        # Existing user — role is persisted, not overwritten from env vars
        if not user.is_active:
            auth_svc_logger.warning("LOGIN_BLOCKED: inactive user_id=%s email=%s", user.id, email)
            return None
        user.email = email
        user.display_name = display_name
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return user

    # --- New user ---

    # 1. Token-based invitation → join as worker
    if invite_token:
        user = User(
            google_id=google_id, email=email,
            display_name=display_name, role='worker',
        )
        db.session.add(user)
        db.session.flush()
        org_id, err = validate_and_accept_invitation(invite_token, user)
        if err:
            db.session.rollback()
            auth_svc_logger.warning("INVITE_REJECTED: token err=%s email=%s", err, email)
            return None
        user.organization_id = org_id
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return user

    # 2. Invite code → join as worker
    if invite_code:
        org, err = resolve_invite_code(invite_code)
        if err:
            auth_svc_logger.warning("INVITE_REJECTED: code err=%s email=%s", err, email)
            return None
        user = User(
            google_id=google_id, email=email,
            display_name=display_name, role='worker',
        )
        user.organization_id = org.id
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return user

    # 3. Check for pending email invitation (direct login case) → join as worker
    pending = check_email_invitation(email)
    if pending:
        user = User(
            google_id=google_id, email=email,
            display_name=display_name, role='worker',
        )
        db.session.add(user)
        db.session.flush()
        org_id = accept_email_invitation(pending, user)
        user.organization_id = org_id
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return user

    # 4. No invitation → create new organization as admin
    org = Organization(
        name=f'{display_name or email} の組織',
        admin_email=email,
    )
    db.session.add(org)
    db.session.flush()

    user = User(
        google_id=google_id, email=email,
        display_name=display_name, role='admin',
    )
    user.organization_id = org.id
    db.session.add(user)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    auth_svc_logger.info(
        "NEW_ORG_CREATED: user=%s email=%s org_id=%s",
        user.id, email, org.id,
    )
    return user


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
