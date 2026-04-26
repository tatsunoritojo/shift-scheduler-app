import logging
import os

os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

app = create_app()

logger = logging.getLogger(__name__)


def _pick_migration_db_url():
    """Pick the best DB URL for Alembic DDL on serverless cold start.

    Priority:
    1. Explicit unpooled vars (Neon integration names vary by project age)
    2. Generic DATABASE_URL fallback
    """
    candidates = [
        ('DATABASE_URL_UNPOOLED', os.environ.get('DATABASE_URL_UNPOOLED')),
        ('DATABASE_POSTGRES_URL_NON_POOLING', os.environ.get('DATABASE_POSTGRES_URL_NON_POOLING')),
        ('POSTGRES_URL_NON_POOLING', os.environ.get('POSTGRES_URL_NON_POOLING')),
        ('DATABASE_URL', os.environ.get('DATABASE_URL')),
    ]
    for name, value in candidates:
        if value:
            return name, value
    return None, None


def _run_auto_migration():
    """Run pending Alembic migrations on cold start."""
    source_env, migration_url = _pick_migration_db_url()

    if not migration_url:
        logger.warning(
            "Auto-migration skipped: DB URL env var not found (tried DATABASE_URL_UNPOOLED, "
            "DATABASE_POSTGRES_URL_NON_POOLING, POSTGRES_URL_NON_POOLING, DATABASE_URL)"
        )
        return

    if source_env == 'DATABASE_URL' and '-pooler' in migration_url:
        logger.warning(
            "Auto-migration is using pooled DATABASE_URL. DDL may be rejected; set an unpooled var."
        )

    # Tell migrations/env.py to use this URL instead of the app's engine.
    os.environ['ALEMBIC_OVERRIDE_DB_URL'] = migration_url
    try:
        from flask_migrate import upgrade
        with app.app_context():
            upgrade()
        logger.info("Auto-migration completed (source_env=%s)", source_env)
    finally:
        os.environ.pop('ALEMBIC_OVERRIDE_DB_URL', None)


try:
    _run_auto_migration()
except Exception as e:
    # Log loudly so the failure is visible (used to be swallowed silently).
    # Keep the app starting so users see endpoint errors instead of full
    # outage; manual intervention is still required to fix the schema.
    logger.error("Auto-migration FAILED: %s", e, exc_info=True)
