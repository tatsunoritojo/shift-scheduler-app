from flask import Blueprint, redirect, request, url_for, session, jsonify, current_app

from app.extensions import limiter
from app.services.auth_service import (
    create_oauth_flow, extract_user_info, upsert_user, save_refresh_token,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


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
    state = session.get('state')
    if not state or state != request.args.get('state'):
        return jsonify({"error": "State mismatch"}), 400

    flow = create_oauth_flow(state=state)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch token: {e}"}), 500

    credentials = flow.credentials
    google_id, email, display_name = extract_user_info(credentials)

    if not google_id:
        return jsonify({"error": "Failed to extract user info"}), 500

    user = upsert_user(google_id, email, display_name)

    if credentials.refresh_token:
        save_refresh_token(user, credentials.refresh_token, credentials.scopes)

    session.permanent = True
    session['user_id'] = user.id
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
    }

    # Redirect based on role
    if user.role == 'admin':
        return redirect('/admin')
    elif user.role == 'owner':
        return redirect('/owner')
    else:
        return redirect('/worker')


@auth_bp.route('/logout')
def logout():
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
