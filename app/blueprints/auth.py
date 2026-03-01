import hmac
import logging
import requests as http_requests

from flask import Blueprint, redirect, request, url_for, session, jsonify, current_app

from app.extensions import db, limiter
from app.utils.errors import error_response
from app.services.auth_service import (
    create_oauth_flow, extract_user_info, upsert_user, save_refresh_token,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
auth_logger = logging.getLogger('auth')


@auth_bp.route('/invite/<token>')
def accept_invite(token):
    """Store invitation token in session and redirect to OAuth login."""
    from app.models.membership import InvitationToken

    invite = InvitationToken.query.filter_by(token=token).first()
    if not invite or not invite.is_valid:
        return error_response("Invalid or expired invitation", 400, code="BAD_REQUEST")

    # If email-restricted, inform the user
    session['invitation_token'] = token
    return redirect(url_for('auth.login'))


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

    # Check for invitation token
    invitation = _resolve_invitation(email)

    user = upsert_user(google_id, email, display_name, invitation_token=invitation)

    if credentials.refresh_token:
        save_refresh_token(user, credentials.refresh_token, credentials.scopes)

    # Prevent session fixation: clear old session before setting auth data
    session.clear()
    session.permanent = True
    session['user_id'] = user.id
    session.pop('invitation_token', None)  # Clean up
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
    }

    auth_logger.info("LOGIN_SUCCESS: user_id=%s email=%s role=%s", user.id, user.email, user.role)

    # Redirect based on org membership
    if not user.organization_id:
        auth_logger.info("LOGIN_NO_ORG: user_id=%s redirected to /no-organization", user.id)
        return redirect('/no-organization')

    if user.role == 'admin':
        return redirect('/admin')
    elif user.role == 'owner':
        return redirect('/owner')
    else:
        return redirect('/worker')


def _resolve_invitation(email):
    """Look up invitation token from session, validate email match."""
    from app.models.membership import InvitationToken

    token_str = session.get('invitation_token')
    if not token_str:
        return None

    invite = InvitationToken.query.filter_by(token=token_str).first()
    if not invite or not invite.is_valid:
        return None

    # If token is email-restricted, check the email matches
    if invite.email and invite.email.lower() != email.lower():
        current_app.logger.warning(
            f"Invitation token email mismatch: expected={invite.email}, got={email}"
        )
        return None

    return invite


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
