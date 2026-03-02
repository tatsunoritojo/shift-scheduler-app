from flask import Blueprint, jsonify, session, current_app, redirect, request

from app.extensions import limiter
from app.middleware.auth_middleware import get_current_user

api_common_bp = Blueprint('api_common', __name__)


@api_common_bp.route('/health')
def health():
    return jsonify({"status": "healthy", "version": "2.0.0"})


@api_common_bp.route('/')
def index():
    user_id = session.get('user_id')
    if user_id:
        user = get_current_user()
        if user:
            if not user.organization_id:
                return redirect('/no-organization')
            if user.role == 'admin':
                return redirect('/admin')
            elif user.role == 'owner':
                return redirect('/owner')
            else:
                return redirect('/worker')
    return redirect('/login')


@api_common_bp.route('/app')
def legacy_app():
    """Serve the original shift calculator app for backwards compatibility."""
    return current_app.send_static_file('shift_scheduler_app.html')


@api_common_bp.route('/lp')
def landing_page():
    return current_app.send_static_file('pages/landing.html')


@api_common_bp.route('/robots.txt')
def robots():
    return current_app.send_static_file('robots.txt')


@api_common_bp.route('/sitemap.xml')
def sitemap():
    return current_app.send_static_file('sitemap.xml')


@api_common_bp.route('/login')
def login_page():
    return current_app.send_static_file('pages/login.html')


@api_common_bp.route('/no-organization')
def no_organization_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if user.organization_id:
        return redirect('/')
    return current_app.send_static_file('pages/no-organization.html')


@api_common_bp.route('/invite')
def invite_page():
    """Serve the invitation landing page."""
    return current_app.send_static_file('pages/invite.html')


@api_common_bp.route('/api/invite/info')
@limiter.limit("20 per minute")
def invite_info():
    """Public API: return organization name for a given invite code or token."""
    from app.models.organization import Organization
    from app.models.membership import InvitationToken

    code = request.args.get('code')
    token = request.args.get('token')

    if code:
        org = Organization.query.filter_by(invite_code=code, invite_code_enabled=True).first()
        if not org or not org.is_active:
            return jsonify({'error': 'Invalid or disabled invite code'}), 404
        login_url = f"/auth/invite/code/{code}"
        return jsonify({
            'organization_name': org.name,
            'role': 'worker',
            'login_url': login_url,
        })

    if token:
        invite = InvitationToken.query.filter_by(token=token).first()
        if not invite or not invite.is_valid:
            return jsonify({'error': 'Invalid or expired invitation'}), 404
        login_url = f"/auth/invite/{token}"
        return jsonify({
            'organization_name': invite.organization.name,
            'role': invite.role,
            'login_url': login_url,
        })

    return jsonify({'error': 'code or token parameter is required'}), 400


@api_common_bp.route('/worker')
def worker_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if not user.organization_id:
        return redirect('/no-organization')
    if user.role != 'worker':
        return redirect('/')
    return current_app.send_static_file('pages/worker.html')


@api_common_bp.route('/admin')
def admin_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if not user.organization_id:
        return redirect('/no-organization')
    if user.role != 'admin':
        return redirect('/')
    return current_app.send_static_file('pages/admin.html')


@api_common_bp.route('/owner')
def owner_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if not user.organization_id:
        return redirect('/no-organization')
    if user.role != 'owner':
        return redirect('/')
    return current_app.send_static_file('pages/owner.html')
