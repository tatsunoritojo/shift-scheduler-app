import os
from datetime import timedelta


class BaseConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Session
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OAuth scopes
    GOOGLE_SCOPES_READONLY = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/calendar.events.readonly',
    ]
    GOOGLE_SCOPES_WRITE = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/calendar.events.readonly',
        'https://www.googleapis.com/auth/calendar.events',
    ]

    def __init__(self):
        # Read env vars at instantiation time (after load_dotenv)
        self.GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
        self.GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')
        self.ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
        self.OWNER_EMAIL = os.environ.get('OWNER_EMAIL', '')

    @staticmethod
    def _get_database_url():
        database_url = os.environ.get('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://')
        return database_url


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in dev

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return self._get_database_url() or 'sqlite:///tokens.db'


class ProductionConfig(BaseConfig):
    DEBUG = False

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return self._get_database_url() or 'sqlite:///tokens.db'


class TestConfig(BaseConfig):
    TESTING = True
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestConfig,
}
