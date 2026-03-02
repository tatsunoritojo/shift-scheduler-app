import hmac
import logging
import requests as http_requests

from flask import Blueprint, redirect, request, url_for, session, jsonify, current_app

from app.extensions import limiter
from app.services.auth_service import (
    create_oauth_flow, extract_user_info, upsert_user, save_refresh_token,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
auth_logger = logging.getLogger('auth')


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

    response = redirect(authorization_url)

    # Store invite params in cookies (survives session.clear())
    invite_token = request.args.get('invite')
    invite_code = request.args.get('invite_code')
    cookie_opts = dict(httponly=True, secure=True, samesite='Lax', max_age=600)
    if invite_token:
        response.set_cookie('invite_token', invite_token, **cookie_opts)
    if invite_code:
        response.set_cookie('invite_code', invite_code, **cookie_opts)

    return response


@auth_bp.route('/google/callback')
@limiter.limit("10 per minute")
def callback():
    # Pop state to ensure one-time use
    state = session.pop('state', None)
    request_state = request.args.get('state', '')
    if not state or not hmac.compare_digest(str(state), str(request_state)):
        auth_logger.warning("LOGIN_FAILED: OAuth state mismatch from %s", request.remote_addr)
        return jsonify({"error": "State mismatch"}), 400

    flow = create_oauth_flow(state=state)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        auth_logger.warning("LOGIN_FAILED: Token fetch failed from %s: %s", request.remote_addr, e)
        return jsonify({"error": "認証に失敗しました。もう一度お試しください。"}), 500

    credentials = flow.credentials
    google_id, email, display_name = extract_user_info(credentials)

    if not google_id:
        auth_logger.warning("LOGIN_FAILED: Could not extract user info from %s", request.remote_addr)
        return jsonify({"error": "Failed to extract user info"}), 500

    # Read invite params from cookies (set in login())
    invite_token = request.cookies.get('invite_token')
    invite_code = request.cookies.get('invite_code')

    user = upsert_user(
        google_id, email, display_name,
        invite_token=invite_token, invite_code=invite_code,
    )

    # Build redirect response first so we can delete cookies
    if not user:
        # upsert_user returns None for: inactive user, or invalid invitation
        from app.models.user import User as UserModel
        existing = UserModel.query.filter_by(email=email).first()
        if existing and not existing.is_active:
            error_type = 'inactive'
        else:
            error_type = 'invalid_invitation'
        auth_logger.warning("LOGIN_BLOCKED: reason=%s email=%s", error_type, email)
        response = redirect(f'/login?error={error_type}')
        response.delete_cookie('invite_token')
        response.delete_cookie('invite_code')
        return response

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

    # Redirect based on role
    if user.role == 'admin':
        response = redirect('/admin')
    elif user.role == 'owner':
        response = redirect('/owner')
    else:
        response = redirect('/worker')

    # Clean up cookies
    response.delete_cookie('invite_token')
    response.delete_cookie('invite_code')
    return response


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
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    })
