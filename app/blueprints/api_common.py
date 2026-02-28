from flask import Blueprint, jsonify, session, current_app, redirect

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


@api_common_bp.route('/login')
def login_page():
    return current_app.send_static_file('pages/login.html')


@api_common_bp.route('/worker')
def worker_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if user.role != 'worker':
        return redirect('/')
    return current_app.send_static_file('pages/worker.html')


@api_common_bp.route('/admin')
def admin_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if user.role != 'admin':
        return redirect('/')
    return current_app.send_static_file('pages/admin.html')


@api_common_bp.route('/owner')
def owner_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if user.role != 'owner':
        return redirect('/')
    return current_app.send_static_file('pages/owner.html')


@api_common_bp.route('/api/debug/routes')
def debug_routes():
    routes = []
    for rule in current_app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule),
        })
    return jsonify(routes)


@api_common_bp.route('/api/debug/session')
def debug_session():
    return jsonify({
        'user_id': session.get('user_id'),
        'has_credentials': 'credentials' in session,
        'session_keys': list(session.keys()),
    })


@api_common_bp.route('/api/debug/auth-check')
def auth_check():
    from app.middleware.auth_middleware import get_current_user
    user = get_current_user()
    if not user:
        return jsonify({
            'authenticated': False,
            'error': 'Not authenticated',
        })
    return jsonify({
        'authenticated': True,
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
    })
