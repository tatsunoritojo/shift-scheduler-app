from flask import Flask
from pathlib import Path
from dotenv import load_dotenv
import os

from app.extensions import db, cors
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

    # Validate Google OAuth credentials
    if not app.config.get('GOOGLE_CLIENT_ID') or not app.config.get('GOOGLE_CLIENT_SECRET'):
        import warnings
        warnings.warn("Google OAuth credentials not configured. OAuth will not work.")

    # Initialize extensions
    db.init_app(app)
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

    # Create tables
    with app.app_context():
        db.create_all()

    return app
