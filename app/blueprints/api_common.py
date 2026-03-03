import logging

from flask import Blueprint, jsonify, session, current_app, redirect, request, make_response

from app.extensions import db, limiter
from app.middleware.auth_middleware import get_current_user, _check_active_membership
from app.utils.errors import error_response

api_common_bp = Blueprint('api_common', __name__)
page_logger = logging.getLogger('pages')


@api_common_bp.route('/health')
def health():
    return jsonify({"status": "healthy", "version": "2.0.0"})


@api_common_bp.route('/')
def index():
    user_id = session.get('user_id')
    if user_id:
        user = get_current_user()
        if user:
            if not user.organization_id or not _check_active_membership(user):
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
    if user.organization_id and _check_active_membership(user):
        return redirect('/')
    return current_app.send_static_file('pages/no-organization.html')


@api_common_bp.route('/api/organizations', methods=['POST'])
@limiter.limit("5 per hour")
def create_organization():
    """Create a new organization. The authenticated user becomes its admin."""
    import logging
    from app.models.organization import Organization
    from app.models.membership import OrganizationMember

    logger = logging.getLogger(__name__)

    user = get_current_user()
    if not user:
        return error_response("Authentication required", 401, code="AUTH_REQUIRED")

    if _check_active_membership(user):
        return error_response("Already a member of an organization", 400, code="ALREADY_MEMBER")

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        name = f'{user.display_name or user.email} の組織'
    if len(name) > 255:
        return error_response("Organization name too long", 400, code="VALIDATION_ERROR")

    try:
        org = Organization(name=name, admin_email=user.email)
        db.session.add(org)
        db.session.flush()

        member = OrganizationMember(
            user_id=user.id,
            organization_id=org.id,
            role='admin',
        )
        db.session.add(member)

        # Sync denormalized fields directly (avoid lazy-load on new member)
        user.role = 'admin'
        user.organization_id = org.id

        # Capture values before commit (commit expires ORM objects)
        org_id = org.id
        org_name = org.name

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to create organization for user %s: %s", user.email, e)
        return error_response("Failed to create organization", 500, code="INTERNAL_ERROR")

    return jsonify({
        'id': org_id,
        'name': org_name,
        'role': 'admin',
    }), 201


@api_common_bp.route('/invite')
def invite_page():
    """Serve the invitation landing page."""
    return current_app.send_static_file('pages/invite.html')


@api_common_bp.route('/callback-landing')
def callback_landing_page():
    """Intermediate page shown after OAuth callback for invite joins."""
    return current_app.send_static_file('pages/callback-landing.html')


@api_common_bp.route('/ui-preview')
def ui_preview_page():
    """Dev-only: preview page for UI components."""
    return current_app.send_static_file('pages/ui-preview.html')


@api_common_bp.route('/api/invite/info')
@limiter.limit("20 per minute")
def invite_info():
    """Public API: return organization name for a given invite code or token."""
    from app.models.organization import Organization
    from app.models.membership import InvitationToken

    code = request.args.get('code')
    token = request.args.get('token')

    if code:
        org = Organization.query.filter_by(invite_code=code).first()
        if not org or not org.is_active:
            return jsonify({'error': 'Invalid invite code', 'code': 'INVITE_CODE_NOT_FOUND'}), 404
        if not org.invite_code_enabled:
            return jsonify({'error': 'Invite code is disabled', 'code': 'INVITE_CODE_DISABLED'}), 403
        login_url = f"/auth/invite/code/{code}"
        return jsonify({
            'organization_name': org.name,
            'role': 'worker',
            'login_url': login_url,
        })

    if token:
        invite = InvitationToken.query.filter_by(token=token).first()
        if not invite:
            return jsonify({'error': 'Invalid invitation', 'code': 'INVITATION_NOT_FOUND'}), 404
        if invite.used_at:
            return jsonify({'error': 'Invitation already used', 'code': 'INVITATION_USED'}), 410
        if not invite.is_valid:
            return jsonify({'error': 'Invitation expired', 'code': 'INVITATION_EXPIRED'}), 410
        login_url = f"/auth/invite/{token}"
        return jsonify({
            'organization_name': invite.organization.name,
            'role': invite.role,
            'login_url': login_url,
        })

    return jsonify({'error': 'code or token parameter is required', 'code': 'MISSING_PARAM'}), 400


@api_common_bp.route('/vacancy/respond')
@limiter.limit("30 per minute")
def vacancy_respond():
    """Public endpoint for candidates to accept/decline vacancy requests."""
    token = request.args.get('token')
    action = request.args.get('action')

    if not token or action not in ('accept', 'decline'):
        return _vacancy_response_page({
            'status': 'invalid',
            'message': '無効なリクエストです。',
        })

    from app.services.vacancy_service import respond_to_vacancy
    result, error = respond_to_vacancy(token, action)

    if error:
        return _vacancy_response_page({
            'status': 'error',
            'message': error,
        })

    return _vacancy_response_page(result)


def _vacancy_response_page(result):
    """Render a simple HTML page for vacancy response results."""
    status = result.get('status', 'error')
    messages = {
        'accepted': ('引き受けました', 'シフトへの出勤が確定しました。ありがとうございます！', '#22c55e'),
        'declined': ('辞退しました', 'ご連絡ありがとうございます。', '#6b7280'),
        'already_accepted': ('すでに引き受け済みです', 'このシフトはすでに引き受けています。', '#3b82f6'),
        'already_filled': ('すでに補充済みです', '他の方がすでにこのシフトを引き受けました。', '#f59e0b'),
        'expired': ('期限切れです', 'このリクエストは期限切れまたはキャンセルされました。', '#ef4444'),
        'invalid': ('無効なリクエスト', result.get('message', '無効なリンクです。'), '#ef4444'),
        'error': ('エラー', result.get('message', 'エラーが発生しました。'), '#ef4444'),
    }
    title, message, color = messages.get(status, messages['error'])

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - シフリー</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background: #f1f5f9; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
.card {{ background: #fff; border-radius: 16px; padding: 48px 32px; max-width: 400px; width: 90%; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
.icon {{ width: 64px; height: 64px; border-radius: 50%; background: {color}20; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; }}
.icon svg {{ width: 32px; height: 32px; color: {color}; }}
h1 {{ font-size: 1.5rem; margin: 0 0 12px; color: #1e293b; }}
p {{ color: #64748b; margin: 0; line-height: 1.6; }}
</style>
</head>
<body>
<div class="card">
<div class="icon">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
{"<path d='M20 6L9 17l-5-5'/>" if status in ('accepted', 'already_accepted') else "<circle cx='12' cy='12' r='10'/><line x1='15' y1='9' x2='9' y2='15'/><line x1='9' y1='9' x2='15' y2='15'/>" if status in ('invalid', 'error', 'expired') else "<path d='M20 6L9 17l-5-5'/>"}
</svg>
</div>
<h1>{title}</h1>
<p>{message}</p>
</div>
</body>
</html>"""
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response


@api_common_bp.route('/worker')
def worker_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    membership = _check_active_membership(user)
    if not user.organization_id or not membership:
        return redirect('/no-organization')
    if user.role != 'worker':
        return redirect('/')
    return current_app.send_static_file('pages/worker.html')


@api_common_bp.route('/admin')
def admin_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if not user.organization_id or not _check_active_membership(user):
        return redirect('/no-organization')
    if user.role != 'admin':
        return redirect('/')
    return current_app.send_static_file('pages/admin.html')


@api_common_bp.route('/owner')
def owner_page():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if not user.organization_id or not _check_active_membership(user):
        return redirect('/no-organization')
    if user.role != 'owner':
        return redirect('/')
    return current_app.send_static_file('pages/owner.html')
