from flask import Flask, jsonify
from pathlib import Path
from dotenv import load_dotenv
import logging
import os

from app.extensions import db, migrate, cors, limiter, server_session
from app.config import config_by_name


def _patch_session_bytes_bug(app):
    """Patch Flask-Session 0.8.0 + Werkzeug 3.1 compatibility bug.

    Flask-Session's SQLAlchemy backend may pass session_id as bytes to
    response.set_cookie(), but Werkzeug 3.1+ requires str values.
    Wrap save_session to decode bytes before set_cookie is called.
    """
    from functools import wraps

    iface = app.session_interface
    original_save = iface.save_session

    @wraps(original_save)
    def safe_save_session(app_arg, session, response, *args, **kwargs):
        orig_set_cookie = response.set_cookie

        def _safe_set_cookie(key, value='', **kw):
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            return orig_set_cookie(key, value, **kw)

        response.set_cookie = _safe_set_cookie
        try:
            return original_save(app_arg, session, response, *args, **kwargs)
        finally:
            response.set_cookie = orig_set_cookie

    iface.save_session = safe_save_session


def create_app(config_name=None):
    """Application factory."""
    # Load .env
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent.parent / 'static'),
        static_url_path='/static',
    )

    # Load config
    config_cls = config_by_name.get(config_name, config_by_name['development'])
    app.config.from_object(config_cls())

    # Configure logging
    log_level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    # Validate Google OAuth credentials
    if not app.config.get('GOOGLE_CLIENT_ID') or not app.config.get('GOOGLE_CLIENT_SECRET'):
        import warnings
        warnings.warn("Google OAuth credentials not configured. OAuth will not work.")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    app.config['SESSION_SQLALCHEMY'] = db
    server_session.init_app(app)
    _patch_session_bytes_bug(app)
    limiter.init_app(app)
    cors_origins = app.config.get('CORS_ALLOWED_ORIGINS')
    if cors_origins:
        cors.init_app(app, origins=cors_origins, supports_credentials=True)
    elif app.debug or app.config.get('TESTING'):
        cors.init_app(app)  # Allow all origins in dev/test only
    else:
        # Production: no CORS_ALLOWED_ORIGINS → same-origin only (no CORS headers)
        logging.getLogger(__name__).warning(
            "CORS_ALLOWED_ORIGINS not set in production — cross-origin requests will be blocked"
        )
        cors.init_app(app, origins=[])

    # Import all models so they are registered with SQLAlchemy
    from app import models  # noqa: F401

    # Register blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.api_calendar import api_calendar_bp
    from app.blueprints.api_common import api_common_bp
    from app.blueprints.api_admin import api_admin_bp
    from app.blueprints.api_worker import api_worker_bp
    from app.blueprints.api_owner import api_owner_bp
    from app.blueprints.api_cron import api_cron_bp
    from app.blueprints.api_dashboard import api_dashboard_bp
    from app.blueprints.api_master import api_master_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_calendar_bp)
    app.register_blueprint(api_common_bp)
    app.register_blueprint(api_admin_bp)
    app.register_blueprint(api_worker_bp)
    app.register_blueprint(api_owner_bp)
    app.register_blueprint(api_cron_bp)
    app.register_blueprint(api_dashboard_bp)
    app.register_blueprint(api_master_bp)

    # Register security headers, error handlers, and teardown
    _register_security_headers(app)
    _register_error_handlers(app)
    _register_teardown(app)

    # Tests build schema via migrations in conftest.py to mirror production
    # (the create_all() shortcut used to bypass dialect-specific migration bugs).
    return app


def _register_security_headers(app):
    """Add security headers to all responses."""

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://unpkg.com"
        )
        return response


def _register_teardown(app):
    """Ensure DB session is cleaned up after each request."""

    @app.teardown_request
    def shutdown_session(exception=None):
        if app.config.get('TESTING'):
            return  # Tests manage their own session lifecycle
        try:
            if exception is not None:
                db.session.rollback()
        except Exception:
            pass
        finally:
            db.session.remove()


def _register_error_handlers(app):
    """Register global error handlers.

    API paths (/api/*) get JSON responses; page routes get HTML error pages
    so users aren't stranded on a raw JSON blob.
    """
    from app.utils.errors import APIError, error_response, render_error_page, wants_json

    def _respond(status, title, message, code, detail=None):
        if wants_json():
            return error_response(message, status, code=code)
        return render_error_page(
            title=title, message=message, status=status, detail=detail,
        )

    @app.errorhandler(APIError)
    def handle_api_error(e):
        return error_response(e.message, e.status_code, e.code, e.details)

    @app.errorhandler(400)
    def bad_request(e):
        return _respond(400, "リクエストが不正です",
                        "入力内容を確認してもう一度お試しください。", "BAD_REQUEST")

    @app.errorhandler(404)
    def not_found(e):
        return _respond(404, "ページが見つかりません",
                        "URLが間違っているか、削除されている可能性があります。", "NOT_FOUND")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _respond(405, "操作が許可されていません",
                        "この画面からの操作はできません。", "METHOD_NOT_ALLOWED")

    @app.errorhandler(415)
    def unsupported_media_type(e):
        return error_response("Unsupported media type", 415, code="UNSUPPORTED_MEDIA_TYPE")

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return _respond(429, "リクエストが多すぎます",
                        "しばらく時間をおいてからもう一度お試しください。",
                        "RATE_LIMIT_EXCEEDED")

    @app.errorhandler(500)
    def internal_server_error(e):
        return _respond(500, "サーバーエラーが発生しました",
                        "時間をおいてから再度お試しください。", "INTERNAL_ERROR")

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        app.logger.exception("Unhandled exception: %s", e)
        detail = str(e) if app.debug else None
        return _respond(500, "サーバーエラーが発生しました",
                        "時間をおいてから再度お試しください。",
                        "INTERNAL_ERROR", detail=detail)
