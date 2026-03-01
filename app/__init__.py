from flask import Flask, jsonify
from pathlib import Path
from dotenv import load_dotenv
import logging
import os

from app.extensions import db, cors, limiter, server_session
from app.config import config_by_name


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
    app.config['SESSION_SQLALCHEMY'] = db
    server_session.init_app(app)
    limiter.init_app(app)
    cors_origins = app.config.get('CORS_ALLOWED_ORIGINS')
    if cors_origins:
        cors.init_app(app, origins=cors_origins, supports_credentials=True)
    else:
        cors.init_app(app)

    # Import all models so they are registered with SQLAlchemy
    from app import models  # noqa: F401

    # Register blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.api_calendar import api_calendar_bp
    from app.blueprints.api_common import api_common_bp
    from app.blueprints.api_admin import api_admin_bp
    from app.blueprints.api_worker import api_worker_bp
    from app.blueprints.api_owner import api_owner_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_calendar_bp)
    app.register_blueprint(api_common_bp)
    app.register_blueprint(api_admin_bp)
    app.register_blueprint(api_worker_bp)
    app.register_blueprint(api_owner_bp)

    # Register security headers and error handlers
    _register_security_headers(app)
    _register_error_handlers(app)

    # Create tables
    with app.app_context():
        db.create_all()

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
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com"
        )
        return response


def _register_error_handlers(app):
    """Register global error handlers that return JSON responses."""

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({"error": "Too many requests"}), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        app.logger.exception("Unhandled exception: %s", e)
        if app.debug:
            return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Internal server error"}), 500
