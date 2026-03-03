import hmac
import logging
import requests as http_requests

from flask import Blueprint, redirect, request, url_for, session, jsonify, current_app, make_response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, limiter
from app.utils.errors import error_response
from app.services.auth_service import (
    create_oauth_flow, extract_user_info, upsert_user, save_refresh_token,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
auth_logger = logging.getLogger('auth')

COOKIE_INVITE_TOKEN = 'invite_token'
COOKIE_INVITE_CODE = 'invite_code'
COOKIE_MAX_AGE = 600  # 10 minutes


def _get_serializer():
    """Return a timed serializer using the app's SECRET_KEY."""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _sign_token(value):
    """Sign a value for cookie storage."""
    return _get_serializer().dumps(value, salt='invite')


def _unsign_token(signed_value, max_age=COOKIE_MAX_AGE):
    """Verify and unsign a cookie value. Returns None on failure."""
    try:
        return _get_serializer().loads(signed_value, salt='invite', max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _set_invite_cookie(response, name, value):
    """Set a signed, HttpOnly cookie for invite data."""
    response.set_cookie(
        name, _sign_token(value),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=current_app.config.get('SESSION_COOKIE_SECURE', True),
    )


def _clear_invite_cookies(response):
    """Remove all invite cookies from the response."""
    for name in (COOKIE_INVITE_TOKEN, COOKIE_INVITE_CODE):
        response.delete_cookie(name)


@auth_bp.route('/invite/<token>')
def accept_invite(token):
    """Validate invitation token, set cookie, and redirect to OAuth login."""
    from app.models.membership import InvitationToken

    invite = InvitationToken.query.filter_by(token=token).first()
    if not invite or not invite.is_valid:
        return error_response("Invalid or expired invitation", 400, code="BAD_REQUEST")

    # Pass token as query param so login() stores it in session with state
    resp = make_response(redirect(url_for('auth.login', invite_token=token)))
    _set_invite_cookie(resp, COOKIE_INVITE_TOKEN, token)
    return resp


@auth_bp.route('/invite/code/<code>')
def accept_invite_code(code):
    """Validate invite_code, set cookie, and redirect to OAuth login."""
    from app.models.organization import Organization

    org = Organization.query.filter_by(invite_code=code, invite_code_enabled=True).first()
    if not org or not org.is_active:
        return error_response("Invalid or disabled invite code", 400, code="BAD_REQUEST")

    # Pass code as query param so login() stores it in session with state
    resp = make_response(redirect(url_for('auth.login', invite_code=code)))
    _set_invite_cookie(resp, COOKIE_INVITE_CODE, code)
    return resp


@auth_bp.route('/google/login')
@limiter.limit("10 per minute")
def login():
    flow = create_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    session['state'] = state

    # Store invite data in session alongside state (same request = guaranteed consistency)
    invite_code = request.args.get('invite_code')
    invite_token = request.args.get('invite_token')
    if invite_code:
        session['invite_code'] = invite_code
    if invite_token:
        session['invitation_token'] = invite_token

    return redirect(authorization_url)


@auth_bp.route('/google/callback')
@limiter.limit("10 per minute")
def callback():
    # Pop state to ensure one-time use
    state = session.pop('state', None)
    request_state = request.args.get('state', '')
    if not state or not hmac.compare_digest(str(state), str(request_state)):
        auth_logger.warning("LOGIN_FAILED: OAuth state mismatch from %s", request.remote_addr)
        return error_response("State mismatch", 400, code="BAD_REQUEST")

    flow = create_oauth_flow(state=state)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        auth_logger.warning("LOGIN_FAILED: Token fetch failed from %s: %s", request.remote_addr, e)
        return error_response("認証に失敗しました。もう一度お試しください。", 500, code="INTERNAL_ERROR")

    credentials = flow.credentials
    google_id, email, display_name = extract_user_info(credentials)

    if not google_id:
        auth_logger.warning("LOGIN_FAILED: Could not extract user info from %s", request.remote_addr)
        return error_response("Failed to extract user info", 500, code="INTERNAL_ERROR")

    # Check for invitation token (cookie → session fallback)
    invitation = _resolve_invitation(email)

    # Check for invite_code (cookie → session fallback)
    invite_code_org = _resolve_invite_code()

    user = upsert_user(google_id, email, display_name,
                       invitation_token=invitation,
                       invite_code_org=invite_code_org)

    if credentials.refresh_token:
        save_refresh_token(user, credentials.refresh_token, credentials.scopes)

    # Prevent session fixation: clear old session before setting auth data
    session.clear()
    session.permanent = True
    session['user_id'] = user.id
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
    }

    auth_logger.info("LOGIN_SUCCESS: user_id=%s email=%s role=%s", user.id, user.email, user.role)

    # Build redirect response and clear invite cookies
    joined_via_invite = invitation is not None or invite_code_org is not None

    if not user.organization_id:
        auth_logger.info("LOGIN_NO_ORG: user_id=%s redirected to /no-organization", user.id)
        dest = '/no-organization'
    elif user.role == 'admin':
        dest = '/admin'
    elif user.role == 'owner':
        dest = '/owner'
    else:
        dest = '/worker'

    if joined_via_invite and user.organization_id:
        from urllib.parse import urlencode
        landing_params = urlencode({'dest': dest, 'joined': '1'})
        resp = make_response(redirect(f'/callback-landing?{landing_params}'))
    else:
        resp = make_response(redirect(dest))
    _clear_invite_cookies(resp)
    return resp


def _resolve_invitation(email):
    """Look up invitation token from cookie, falling back to session."""
    from app.models.membership import InvitationToken

    # Try cookie first
    signed = request.cookies.get(COOKIE_INVITE_TOKEN)
    if signed:
        token_str = _unsign_token(signed)
        if token_str:
            invite = InvitationToken.query.filter_by(token=token_str).first()
            if invite and invite.is_valid:
                if invite.email and invite.email.lower() != email.lower():
                    current_app.logger.warning(
                        "Invitation token email mismatch: expected=%s, got=%s",
                        invite.email, email,
                    )
                    return None
                return invite

    # Fallback to session (backward compatibility)
    token_str = session.get('invitation_token')
    if not token_str:
        return None

    invite = InvitationToken.query.filter_by(token=token_str).first()
    if not invite or not invite.is_valid:
        return None

    if invite.email and invite.email.lower() != email.lower():
        current_app.logger.warning(
            "Invitation token email mismatch: expected=%s, got=%s",
            invite.email, email,
        )
        return None

    return invite


def _resolve_invite_code():
    """Resolve invite_code from cookie, falling back to session."""
    from app.models.organization import Organization

    # Try cookie first
    signed = request.cookies.get(COOKIE_INVITE_CODE)
    if signed:
        code = _unsign_token(signed)
        if code:
            org = Organization.query.filter_by(invite_code=code, invite_code_enabled=True).first()
            if org and org.is_active:
                return org

    # Fallback to session (mobile browsers may lose cookies during OAuth redirect)
    code = session.get('invite_code')
    if not code:
        return None

    org = Organization.query.filter_by(invite_code=code, invite_code_enabled=True).first()
    if not org or not org.is_active:
        return None

    return org


@auth_bp.route('/logout')
def logout():
    # Revoke Google token (best-effort)
    creds = session.get('credentials', {})
    token = creds.get('token')
    user_id = session.get('user_id')
    if token:
        try:
            http_requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': token},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=5,
            )
        except Exception:
            pass  # best-effort

    auth_logger.info("LOGOUT: user_id=%s", user_id)
    session.clear()
    return redirect('/')


@auth_bp.route('/me')
def me():
    from app.middleware.auth_middleware import get_current_user
    user = get_current_user()
    if not user:
        return error_response("Not authenticated", 401, code="AUTH_REQUIRED")
    return jsonify({
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "organization_id": user.organization_id,
    })
